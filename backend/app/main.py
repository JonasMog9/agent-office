"""FastAPI app.

Routes for /telegram and /ws/events land in later phases.
"""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import SessionLocal, get_session
from app.ingest.apple_routes import router as apple_router
from app.ingest.routes import router as ingest_router
from app.ingest.service import reassign_night_samples
from app.ingest.strava_routes import resume_unfinished_backfill
from app.ingest.strava_routes import router as strava_router
from app.metrics.daily import recompute_all

log = logging.getLogger(__name__)


def _startup_rebuild() -> None:
    """Fix stored data a rule change left on the wrong day, then rebuild every score."""
    try:
        with SessionLocal() as session:
            reassign_night_samples(session, get_settings().timezone)
    except Exception:  # noqa: BLE001  (never take the app down over a repair)
        log.exception("Reassigning night samples failed")
    recompute_all(SessionLocal)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    resume_unfinished_backfill()  # a redeploy kills background threads; pick the import back up
    # Rebuild every stored score in the background, so formula changes apply after a deploy.
    threading.Thread(target=_startup_rebuild, daemon=True).start()
    yield


app = FastAPI(title="Agent Office", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingest_router)
app.include_router(strava_router)
app.include_router(apple_router)


@app.get("/health")
def health(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
    """Liveness plus a database round trip. Railway's healthcheck calls this on every deploy.

    ``migration`` is the Alembic revision the database is on, so a deploy whose migrations
    didn't run is visible from a browser.
    """
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    try:
        migration = session.scalar(text("SELECT version_num FROM alembic_version")) or "none"
    except SQLAlchemyError:
        session.rollback()
        migration = "none"
    return JSONResponse({"status": "ok", "database": "ok", "migration": migration})
