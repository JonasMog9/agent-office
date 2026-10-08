"""POST /ingest/health: the iOS Shortcut's daily upload."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session
from app.ingest.service import ingest_shortcut_payload

router = APIRouter()


def require_ingest_secret(
    x_ingest_secret: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().ingest_secret
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "INGEST_SECRET is not set")
    if not x_ingest_secret or not hmac.compare_digest(x_ingest_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad or missing X-Ingest-Secret")


@router.post("/ingest/health", dependencies=[Depends(require_ingest_secret)])
def ingest_health(
    body: Annotated[dict, Body()],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    result = ingest_shortcut_payload(session, body)
    days = sorted({s.day for s in result.samples})
    return {
        "samples": len(result.samples),
        "days_updated": [d.isoformat() for d in days],
        "skipped": result.skipped[:20],
        "skipped_count": len(result.skipped),
        "unknown_fields": result.unknown_fields,
    }
