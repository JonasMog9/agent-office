import os
import tempfile
from collections.abc import Iterator

import pytest

# Point the app at a throwaway SQLite file before any app module creates its engine.
_db_dir = tempfile.mkdtemp(prefix="agent-office-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_dir}/test.db"

from app.config import get_settings  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.session import Base, engine  # noqa: E402


@pytest.fixture
def db() -> Iterator[None]:
    """Fresh tables for one test."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def ingest_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    secret = "test-ingest-secret"
    monkeypatch.setenv("INGEST_SECRET", secret)
    get_settings.cache_clear()
    yield secret
    get_settings.cache_clear()
