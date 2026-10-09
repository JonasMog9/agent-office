from collections.abc import Iterator
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.models import StravaToken, Workout
from app.db.session import SessionLocal
from app.ingest import strava_routes
from app.ingest.strava import RateLimited, StravaClient, workout_from_activity
from app.ingest.strava_service import NotConnected, access_token, backfill
from app.main import app
from tests.ingest.fake_strava import OWNER, FakeStrava, activity


@pytest.fixture
def strava_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key, value in {
        "STRAVA_CLIENT_ID": "123",
        "STRAVA_CLIENT_SECRET": "client-secret",
        "STRAVA_ATHLETE_ID": str(OWNER),
        "STRAVA_WEBHOOK_VERIFY_TOKEN": "verify-me",
        "RAILWAY_PUBLIC_DOMAIN": "office.example.app",
        "STRAVA_REFRESH_TOKEN": "",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Clock:
    def __init__(self, t: float = 1_900_000_000) -> None:
        self.t = t
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


@pytest.fixture
def fake() -> FakeStrava:
    return FakeStrava()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(fake: FakeStrava, clock: Clock) -> StravaClient:
    return StravaClient(
        httpx.Client(transport=fake.client_transport()), sleep=clock.sleep, now=clock.now
    )


@pytest.fixture
def api(client: StravaClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    started: list[StravaClient] = []
    monkeypatch.setattr(strava_routes, "start_backfill", started.append)
    app.dependency_overrides[strava_routes.get_client] = lambda: client
    test_client = TestClient(app, follow_redirects=False)
    test_client.backfills_started = started  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def connected(expires_at: int = 2_000_000_000) -> None:
    with SessionLocal() as s:
        s.add(
            StravaToken(
                athlete_id=OWNER, access_token="a0", refresh_token="r0", expires_at=expires_at
            )
        )
        s.commit()


def stored(activity_id: int) -> Workout | None:
    with SessionLocal() as s:
        return s.get(Workout, activity_id)


# --- mapping -----------------------------------------------------------------------------


def test_activity_maps_to_workout_columns_using_the_local_day() -> None:
    late = activity(1, day="2026-10-07") | {
        "start_date": "2026-10-08T02:30:00Z",  # 22:30 local, already the 8th in UTC
        "start_date_local": "2026-10-07T22:30:00Z",
    }
    row = workout_from_activity(late, {"heartrate": [150]})
    assert row["day"] == date(2026, 10, 7)
    assert (row["sport_type"], row["distance_m"], row["avg_hr"]) == ("Run", 10000.0, 150.0)
    assert row["summary"]["best_efforts"][0]["name"] == "5k"
    assert row["streams"] == {"heartrate": [150]}


# --- tokens ------------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "strava_env")
def test_valid_token_is_used_without_refreshing(client: StravaClient, fake: FakeStrava) -> None:
    connected()
    with SessionLocal() as s:
        assert access_token(s, client) == "a0"
    assert fake.refresh_count == 0


@pytest.mark.usefixtures("db", "strava_env")
def test_expired_token_is_refreshed_and_the_rotated_refresh_token_saved(
    client: StravaClient, fake: FakeStrava, clock: Clock
) -> None:
    connected(expires_at=int(clock.t) + 60)  # inside the 2-minute safety margin
    with SessionLocal() as s:
        assert access_token(s, client) == "access-r1"
        row = s.get(StravaToken, OWNER)
        assert (row.refresh_token, row.expires_at) == ("refresh-r1", 2_000_000_000)


@pytest.mark.usefixtures("db", "strava_env")
def test_not_connected_without_a_token(client: StravaClient) -> None:
    with SessionLocal() as s, pytest.raises(NotConnected):
        access_token(s, client)


@pytest.mark.usefixtures("db", "strava_env")
def test_env_refresh_token_bootstraps_the_connection(
    client: StravaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRAVA_REFRESH_TOKEN", "from-env")
    get_settings.cache_clear()
    with SessionLocal() as s:
        assert access_token(s, client) == "access-r1"
        assert s.get(StravaToken, OWNER).refresh_token == "refresh-r1"


# --- rate limits -------------------------------------------------------------------------


def test_short_term_429_waits_for_the_next_quarter_hour(
    client: StravaClient, fake: FakeStrava, clock: Clock
) -> None:
    fake.activities[5] = activity(5)
    fake.rate_limit_next = ["short"]
    clock.t = 1_900_000_000 + 100  # 100 s past a quarter hour
    assert client.get_activity("t", 5)["id"] == 5
    assert clock.slept == [900 - ((1_900_000_000 + 100) % 900) + 5]


def test_daily_429_raises_instead_of_waiting(
    client: StravaClient, fake: FakeStrava, clock: Clock
) -> None:
    fake.rate_limit_next = ["daily"]
    with pytest.raises(RateLimited) as err:
        client.get_activity("t", 5)
    assert err.value.daily and clock.slept == []


# --- connect + callback --------------------------------------------------------------------


@pytest.mark.usefixtures("db", "strava_env")
def test_connect_redirects_to_strava_with_the_public_callback(api: TestClient) -> None:
    response = api.get("/strava/connect")
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://www.strava.com/oauth/authorize?")
    assert "client_id=123" in location
    assert "redirect_uri=https%3A%2F%2Foffice.example.app%2Fstrava%2Fcallback" in location
    assert "activity%3Aread_all" in location


def _state() -> str:
    return strava_routes._state()


@pytest.mark.usefixtures("db", "strava_env")
def test_callback_connects_subscribes_and_starts_backfill(
    api: TestClient, fake: FakeStrava
) -> None:
    response = api.get(
        "/strava/callback",
        params={"state": _state(), "code": "c", "scope": "read,activity:read_all"},
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as s:
        row = s.get(StravaToken, OWNER)
        assert (row.access_token, row.refresh_token, row.subscription_id) == (
            "access-1",
            "refresh-1",
            777,
        )
    assert fake.subscriptions[0]["callback_url"] == "https://office.example.app/strava/webhook"
    assert len(api.backfills_started) == 1  # type: ignore[attr-defined]


@pytest.mark.usefixtures("db", "strava_env")
def test_callback_reuses_an_existing_subscription(api: TestClient, fake: FakeStrava) -> None:
    fake.subscriptions = [{"id": 555}]
    api.get(
        "/strava/callback", params={"state": _state(), "code": "c", "scope": "activity:read_all"}
    )
    assert stored_sub() == 555 and len(fake.subscriptions) == 1


def stored_sub() -> int | None:
    with SessionLocal() as s:
        return s.get(StravaToken, OWNER).subscription_id


@pytest.mark.usefixtures("db", "strava_env")
def test_callback_rejects_someone_elses_strava_account(api: TestClient, fake: FakeStrava) -> None:
    fake.token_athlete = 999
    response = api.get(
        "/strava/callback", params={"state": _state(), "code": "c", "scope": "activity:read_all"}
    )
    assert response.status_code == 403
    with SessionLocal() as s:
        assert s.query(StravaToken).count() == 0


@pytest.mark.usefixtures("db", "strava_env")
@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"state": "123.forged", "code": "c", "scope": "activity:read_all"}, 400),
        ({"code": "c", "scope": "read"}, 400),  # activity permission not granted
        ({"error": "access_denied"}, 400),
    ],
)
def test_callback_rejects_bad_requests(api: TestClient, params: dict, status: int) -> None:
    params = {"state": _state()} | params
    assert api.get("/strava/callback", params=params).status_code == status


# --- webhook -----------------------------------------------------------------------------


@pytest.mark.usefixtures("db", "strava_env")
def test_webhook_validation_echoes_the_challenge(api: TestClient) -> None:
    ok = {"hub.mode": "subscribe", "hub.challenge": "abc", "hub.verify_token": "verify-me"}
    assert api.get("/strava/webhook", params=ok).json() == {"hub.challenge": "abc"}
    assert api.get("/strava/webhook", params=ok | {"hub.verify_token": "nope"}).status_code == 403


def event(aspect: str, activity_id: int = 7, owner: int = OWNER, **extra: object) -> dict:
    return {
        "object_type": "activity",
        "object_id": activity_id,
        "aspect_type": aspect,
        "owner_id": owner,
    } | extra


@pytest.mark.usefixtures("db", "strava_env")
def test_create_event_imports_the_activity_with_streams(api: TestClient, fake: FakeStrava) -> None:
    connected()
    fake.activities[7] = activity(7)
    assert api.post("/strava/webhook", json=event("create")).status_code == 200
    workout = stored(7)
    assert workout.distance_m == 10000.0 and workout.streams["heartrate"] == [140, 141, 142]


@pytest.mark.usefixtures("db", "strava_env")
def test_update_event_refreshes_the_stored_activity(api: TestClient, fake: FakeStrava) -> None:
    connected()
    fake.activities[7] = activity(7)
    api.post("/strava/webhook", json=event("create"))
    fake.activities[7]["name"] = "Long run"
    api.post("/strava/webhook", json=event("update"))
    assert stored(7).name == "Long run"


@pytest.mark.usefixtures("db", "strava_env")
def test_events_for_other_athletes_are_ignored(api: TestClient, fake: FakeStrava) -> None:
    connected()
    fake.activities[7] = activity(7, owner=999)
    api.post("/strava/webhook", json=event("create", owner=999))
    assert stored(7) is None and fake.calls == []


@pytest.mark.usefixtures("db", "strava_env")
def test_delete_only_happens_once_strava_confirms_it(api: TestClient, fake: FakeStrava) -> None:
    connected()
    fake.activities[7] = activity(7)
    api.post("/strava/webhook", json=event("create"))
    api.post("/strava/webhook", json=event("delete"))  # forged: Strava still has it
    assert stored(7) is not None
    del fake.activities[7]
    api.post("/strava/webhook", json=event("delete"))
    assert stored(7) is None


@pytest.mark.usefixtures("db", "strava_env")
def test_deauthorization_removes_the_token(api: TestClient) -> None:
    connected()
    api.post(
        "/strava/webhook",
        json={
            "object_type": "athlete",
            "object_id": OWNER,
            "aspect_type": "update",
            "owner_id": OWNER,
            "updates": {"authorized": "false"},
        },
    )
    with SessionLocal() as s:
        assert s.get(StravaToken, OWNER) is None


# --- backfill + status ---------------------------------------------------------------------


@pytest.mark.usefixtures("db", "strava_env")
def test_backfill_imports_everything_and_skips_what_it_already_has(
    client: StravaClient, fake: FakeStrava, api: TestClient
) -> None:
    connected()
    for i in range(1, 151):  # two pages of 100
        fake.activities[i] = activity(i)
    assert backfill(SessionLocal, client) == 150
    fake.calls.clear()
    assert backfill(SessionLocal, client) == 0  # nothing new: only the list pages are fetched
    assert all("athlete/activities" in c for c in fake.calls)
    status = api.get("/strava/status").json()
    assert status["workouts"] == 150
    assert (status["backfill"]["status"], status["backfill"]["imported"]) == ("done", 0)
    assert status["backfill"]["last_progress_at"]


@pytest.mark.usefixtures("db", "strava_env")
def test_backfill_pauses_at_the_daily_limit_and_resumes(
    client: StravaClient, fake: FakeStrava
) -> None:
    connected()
    for i in range(1, 4):
        fake.activities[i] = activity(i)
    # list page, activity 1, streams 1, then the daily limit hits on activity 2.
    original = fake.handle

    def limited(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/activities/2":
            fake.rate_limit_next.append("daily")
        return original(request)

    fake.handle = limited  # type: ignore[method-assign]
    client.http = httpx.Client(transport=httpx.MockTransport(fake.handle))
    assert backfill(SessionLocal, client) == 1
    with SessionLocal() as s:
        assert s.get(StravaToken, OWNER).backfill_status.startswith("paused")
    fake.handle = original  # type: ignore[method-assign]
    client.http = httpx.Client(transport=fake.client_transport())
    assert backfill(SessionLocal, client) == 2
    assert all(stored(i) is not None for i in (1, 2, 3))


@pytest.mark.usefixtures("db", "strava_env")
def test_status_before_connecting(api: TestClient) -> None:
    body = api.get("/strava/status").json()
    assert body["connected"] is False and body["workouts"] == 0


@pytest.mark.usefixtures("db", "strava_env")
def test_callback_error_text_is_escaped(api: TestClient) -> None:
    body = api.get("/strava/callback", params={"error": "<script>alert(1)</script>"}).text
    assert "<script>" not in body and "&lt;script&gt;" in body


@pytest.mark.usefixtures("db", "strava_env")
def test_backfill_status_says_when_it_is_waiting_on_the_rate_limit(
    client: StravaClient, fake: FakeStrava, clock: Clock
) -> None:
    connected()
    fake.activities[1] = activity(1)
    statuses: list[str] = []
    real_sleep = client.sleep

    def sleep_and_record(seconds: float) -> None:
        with SessionLocal() as s:
            statuses.append(s.get(StravaToken, OWNER).backfill_status)
        real_sleep(seconds)

    client.sleep = sleep_and_record
    clock.t = 1_900_000_800  # a quarter-hour boundary: 18:00 UTC, so it waits until 18:15
    fake.rate_limit_next = ["short"]
    assert backfill(SessionLocal, client) == 1
    assert statuses == ["waiting for Strava rate limit until 18:15 UTC"]


@pytest.mark.usefixtures("db", "strava_env")
def test_only_one_backfill_runs_at_a_time(client: StravaClient) -> None:
    from app.ingest import strava_service

    connected()
    assert strava_service._backfill_lock.acquire()
    try:
        assert backfill(SessionLocal, client) == -1
    finally:
        strava_service._backfill_lock.release()


@pytest.mark.usefixtures("db", "strava_env")
@pytest.mark.parametrize(
    ("status", "resumes"),
    [
        ("running", True),
        ("waiting for Strava rate limit until 10:15 UTC", True),
        ("paused: daily rate limit, resumes on the next restart or reconnect", True),
        ("done", False),
        ("failed", False),
    ],
)
def test_startup_resumes_an_unfinished_import(
    monkeypatch: pytest.MonkeyPatch, status: str, resumes: bool
) -> None:
    connected()
    with SessionLocal() as s:
        s.get(StravaToken, OWNER).backfill_status = status
        s.commit()
    started: list[object] = []
    monkeypatch.setattr(strava_routes, "start_backfill", started.append)
    assert strava_routes.resume_unfinished_backfill() is resumes
    assert len(started) == int(resumes)


@pytest.mark.usefixtures("strava_env")
def test_startup_resume_never_raises_without_tables() -> None:
    assert strava_routes.resume_unfinished_backfill() is False
