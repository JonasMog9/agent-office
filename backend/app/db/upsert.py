"""INSERT ... ON CONFLICT that works on both Postgres (production) and SQLite (tests)."""

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session


def insert_for(session: Session, table):  # noqa: ANN001, ANN201
    dialect = session.get_bind().dialect.name
    return (pg_insert if dialect == "postgresql" else sqlite_insert)(table)
