from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.models import AppState, DailyScore
from app.db.session import SessionLocal
from app.main import app
from app.telegram import morning, routes
from app.telegram.bot import TelegramBot, to_telegram_html

OWNER = 111
SECRET = "tg-secret"
NY = ZoneInfo("America/New_York")


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_OWNER_USER_ID", str(OWNER))
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TIMEZONE", "America/New_York")
    get_settings.cache_clear()
    routes._seen.clear()
    yield
    get_settings.cache_clear()


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def send(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    def typing(self, chat_id: int) -> None:
        pass


def update(uid: int, sender: int, text: str) -> dict:
    return {
        "update_id": uid,
        "message": {"from": {"id": sender}, "chat": {"id": sender}, "text": text},
    }


def post(body: dict, secret: str | None = SECRET):  # noqa: ANN201
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret else {}
    return TestClient(app).post("/telegram", json=body, headers=headers)


@pytest.mark.usefixtures("configured")
def test_owner_gets_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBot()
    monkeypatch.setattr(routes, "bot", lambda: fake)
    monkeypatch.setattr(routes, "answer", lambda text: f"answer to {text}")
    assert post(update(1, OWNER, "How recovered am I?")).status_code == 200
    assert fake.sent == [(OWNER, "answer to How recovered am I?")]


@pytest.mark.usefixtures("configured")
def test_strangers_and_bad_secrets_get_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBot()
    monkeypatch.setattr(routes, "bot", lambda: fake)
    monkeypatch.setattr(routes, "answer", lambda text: "secret health data")
    assert post(update(2, 999, "hi")).status_code == 200  # 200 so Telegram stops retrying
    assert post(update(3, OWNER, "hi"), secret="wrong").status_code == 401
    assert post(update(4, OWNER, "hi"), secret=None).status_code == 401
    assert fake.sent == []


@pytest.mark.usefixtures("configured")
def test_retried_updates_are_answered_once_and_help_is_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeBot()
    calls = []
    monkeypatch.setattr(routes, "bot", lambda: fake)
    monkeypatch.setattr(routes, "answer", lambda text: calls.append(text) or "a")
    post(update(5, OWNER, "q"))
    post(update(5, OWNER, "q"))
    post(update(6, OWNER, "/start"))
    assert calls == ["q"] and len(fake.sent) == 2 and "Agent Office" in fake.sent[1][1]


@pytest.mark.usefixtures("configured")
def test_errors_get_a_polite_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBot()
    monkeypatch.setattr(routes, "bot", lambda: fake)
    monkeypatch.setattr(routes, "answer", lambda text: 1 / 0)
    post(update(7, OWNER, "q"))
    assert "something went wrong" in fake.sent[0][1]


def test_markdown_becomes_safe_telegram_html() -> None:
    out = to_telegram_html("**Recovery:** 77 <green>\n- HRV 70 & up")
    assert out == "<b>Recovery:</b> 77 &lt;green&gt;\n• HRV 70 &amp; up"
    assert len(to_telegram_html("x" * 5000)) == 4096


def test_bot_calls_the_api_without_leaking_the_token() -> None:
    class Http:
        def __init__(self) -> None:
            self.calls = []

        def post(self, url: str, json: dict):  # noqa: ANN201
            self.calls.append((url, json))
            ok = json.get("chat_id") != 0

            class R:
                @staticmethod
                def json() -> dict:
                    return {"ok": ok, "description": "chat not found"}

            return R()

    http = Http()
    b = TelegramBot("123:abc", http)
    b.send(5, "**hi**")
    assert http.calls[0] == (
        "https://api.telegram.org/bot123:abc/sendMessage",
        {"chat_id": 5, "text": "<b>hi</b>", "parse_mode": "HTML"},
    )
    with pytest.raises(RuntimeError) as err:
        b.send(0, "x")
    assert "123:abc" not in str(err.value)


def at(hour: int) -> datetime:
    return datetime(2026, 10, 13, hour, 0, tzinfo=NY)


@pytest.mark.usefixtures("db", "configured")
def test_morning_summary_waits_for_todays_data_then_sends_once() -> None:
    sent, asked = [], []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return "summary"

    def go(hour: int) -> bool:
        return morning.maybe_send(SessionLocal, ask, lambda c, t: sent.append((c, t)), at(hour))

    assert not go(5)  # before the earliest hour
    assert not go(7)  # no data yet, before the fallback
    with SessionLocal() as s:
        s.add(DailyScore(day=date(2026, 10, 13), recovery=60, recovery_label="yellow", details={}))
        s.commit()
    assert go(8) and sent == [(OWNER, "summary")]
    assert not go(9)  # once a day
    assert "hasn't arrived" not in asked[0]


@pytest.mark.usefixtures("db", "configured")
def test_morning_fallback_says_the_data_is_missing() -> None:
    asked = []
    assert morning.maybe_send(
        SessionLocal, lambda p: asked.append(p) or "s", lambda c, t: None, at(10)
    )
    assert "hasn't arrived" in asked[0]
    with SessionLocal() as s:
        assert s.get(AppState, morning.KEY).value == "2026-10-13"


@pytest.mark.usefixtures("db")
def test_no_telegram_no_summary() -> None:
    assert not morning.maybe_send(SessionLocal, lambda p: "s", lambda c, t: None, at(10))
