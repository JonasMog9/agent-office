import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.session import SessionLocal
from app.evals import world
from app.main import app

KEY = "k" * 24


@pytest.fixture
def client(db, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001, ANN201
    monkeypatch.setenv("OFFICE_VIEW_KEY", KEY)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


def test_needs_the_office_key(client: TestClient) -> None:
    assert client.get("/stats/health").status_code == 401
    assert client.get("/stats/health", headers={"X-Office-Key": "nope"}).status_code == 401


def test_an_empty_database_still_answers(client: TestClient) -> None:
    body = client.get("/stats/health", headers={"X-Office-Key": KEY}).json()
    assert body["summary"]["vo2max"] is None and body["records"] == [] and body["plan"] is None
    assert len(body["weekly"]) == 52 and all(w["km"] == 0 for w in body["weekly"])
    assert [p["seconds"] for p in body["predictions"]["current"]] == [None] * 4


def test_the_eval_world_fills_every_section(client: TestClient) -> None:
    with SessionLocal() as s:
        world.build(s)
    body = client.get("/stats/health", headers={"X-Office-Key": KEY}).json()
    s = body["summary"]
    assert s["vo2max"] > 50 and s["label"] == "red" and s["resting_hr"] and s["hrv"]
    assert (
        body["totals"]["all_time"]["runs"] > 40 and body["totals"]["all_time"]["longest_km"] == 21
    )
    assert body["vo2max"][-1]["day"] == body["today"]
    current = {p["distance"]: p for p in body["predictions"]["current"]}
    assert current["10K"]["seconds"] and current["10K"]["methods"]
    assert body["predictions"]["history"]["5K"]
    zones = body["zones"]
    assert [z["zone"] for z in zones["hr"]] == [1, 2, 3, 4, 5]
    assert sum(z["minutes"] for z in zones["hr"]) > 60  # the last 4 weeks of runs, timed
    assert zones["pace"][0]["name"] == "easy" and zones["vdot"]
    assert len(body["calendar"]) == 84 and len(body["vitals"]) == 90 and len(body["sleep"]) == 30
    assert body["runs"][0]["day"] >= body["runs"][-1]["day"]
    assert body["plan"]["this_week"]["workouts"]
