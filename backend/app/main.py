"""FastAPI app.

Routes for /strava/webhook, /telegram and /ws/events land in later phases.
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session
from app.ingest.routes import router as ingest_router

app = FastAPI(title="Agent Office")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingest_router)


@app.get("/health")
def health(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
    """Liveness plus a database round trip. Railway's healthcheck calls this on every deploy."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "ok"})
