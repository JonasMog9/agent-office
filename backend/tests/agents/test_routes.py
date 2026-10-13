import pytest
from fastapi.testclient import TestClient

from app.agents import routes
from app.config import get_settings
from app.main import app
from tests.agents.fake_claude import FakeClaude, reply


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch, ingest_secret: str) -> str:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    yield ingest_secret
    get_settings.cache_clear()


def test_form_and_wrong_secret(keys: str) -> None:
    client = TestClient(app)
    assert "Ask the Manager" in client.get("/agents/ask").text
    r = client.post("/agents/ask", data={"secret": "nope", "question": "hi"})
    assert r.status_code == 401


def test_answer_and_event_log_are_escaped(keys: str, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClaude({"claude-haiku-5-5": [reply(("text", "Hello <b>owner</b>"))]})
    monkeypatch.setattr(routes, "anthropic_client", lambda: fake)
    r = TestClient(app).post("/agents/ask", data={"secret": keys, "question": "<script>x</script>"})
    assert r.status_code == 200
    assert "Hello &lt;b&gt;owner&lt;/b&gt;" in r.text and "<script>x" not in r.text
    assert "talking" in r.text


def test_an_api_error_is_shown_not_a_bare_500(keys: str, monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):  # noqa: ANN003, ANN205
                raise RuntimeError("invalid model: claude-haiku-5-5")

    monkeypatch.setattr(routes, "anthropic_client", lambda: Broken())
    r = TestClient(app).post("/agents/ask", data={"secret": keys, "question": "hi"})
    assert r.status_code == 500
    assert "RuntimeError: invalid model" in r.text and "thinking" in r.text  # partial log too
