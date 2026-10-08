"""POST /ingest/health: the iOS Shortcut's daily upload."""

import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session
from app.ingest.service import ingest_shortcut_payload

log = logging.getLogger(__name__)
router = APIRouter()


def require_ingest_secret(
    x_ingest_secret: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().ingest_secret
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "INGEST_SECRET is not set")
    if not x_ingest_secret or not hmac.compare_digest(x_ingest_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad or missing X-Ingest-Secret")


@router.post("/ingest/health", dependencies=[Depends(require_ingest_secret)], response_model=None)
def ingest_health(
    body: Annotated[dict, Body()],
    session: Annotated[Session, Depends(get_session)],
) -> dict | JSONResponse:
    try:
        result = ingest_shortcut_payload(session, body)
    except Exception as err:  # noqa: BLE001
        # The caller already proved it holds INGEST_SECRET, so it may see what went wrong:
        # the Shortcut's notification is the only place the owner sees this response.
        log.exception("ingest failed")
        session.rollback()
        return JSONResponse(
            {"error": f"{type(err).__name__}: {str(err).splitlines()[0][:300]}"}, status_code=500
        )
    days = sorted({s.day for s in result.samples})
    return {
        "samples": len(result.samples),
        "days_updated": [d.isoformat() for d in days],
        "skipped": result.skipped[:20],
        "skipped_count": len(result.skipped),
        "unknown_fields": result.unknown_fields,
    }
