import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.agents.events import bus
from app.config import get_settings
from app.main import app

KEY = "office-key-123"


@pytest.fixture
def view_key(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    monkeypatch.setenv("OFFICE_VIEW_KEY", KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("view_key")
def test_streams_recent_then_live_events() -> None:
    bus.emit("manager", "idle", None, "before", "w0")
    with TestClient(app).websocket_connect(f"/ws/events?key={KEY}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["recent"][-1]["text"] == "before"
        bus.emit("health_coach", "working", "get_recovery", "Checking recovery", "w1")
        msg = ws.receive_json()
        assert msg["type"] == "event"
        assert msg["event"]["agent"] == "health_coach"
        assert msg["event"]["target"] == "get_recovery" and msg["event"]["run_id"] == "w1"


@pytest.mark.usefixtures("view_key")
def test_wrong_or_missing_key_is_refused() -> None:
    for url in ("/ws/events", "/ws/events?key=nope"):
        # The handshake succeeds, so the browser sees the 4401 close code itself (a refusal
        # during the handshake arrives as a generic failure, and the page would just retry).
        with TestClient(app).websocket_connect(url) as ws:
            with pytest.raises(WebSocketDisconnect) as err:
                ws.receive_json()
        assert err.value.code == 4401


def test_no_key_configured_means_no_live_feed() -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        TestClient(app).websocket_connect("/ws/events?key=x") as ws,
    ):
        ws.receive_json()
