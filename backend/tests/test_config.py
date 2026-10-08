import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@host:5432/db", "postgresql://u:p@host:5432/db"],
)
def test_railway_postgres_urls_use_psycopg_driver(given: str) -> None:
    assert Settings(database_url=given).database_url == "postgresql+psycopg://u:p@host:5432/db"


@pytest.mark.parametrize(
    "given",
    ["postgresql+psycopg://u:p@host:5432/db", "sqlite://", "sqlite:///./agent_office.db"],
)
def test_other_urls_are_left_alone(given: str) -> None:
    assert Settings(database_url=given).database_url == given
