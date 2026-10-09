"""Upload page for Apple Health's "Export All Health Data" zip (one-off history backfill)."""

import hmac
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.db.session import SessionLocal
from app.ingest.apple_export import ExportStats, iter_samples, open_export_xml
from app.ingest.service import recompute_days, store_samples
from app.metrics.daily import recompute_all

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest/apple-export")

# One import at a time; progress lives in memory (this is a one-off, run while you watch).
_lock = threading.Lock()
STATE: dict = {"status": "idle"}

FORM = """<!doctype html><meta name=viewport content='width=device-width'>
<title>Apple Health import</title>
<h2>Import Apple Health history</h2>
<p>On your iPhone: Health → your picture → <b>Export All Health Data</b>, save
<code>export.zip</code> to Files, then pick it here. Big exports take a few minutes to upload.</p>
<form method=post enctype=multipart/form-data>
<p><label>Ingest secret<br><input name=secret type=password required></label></p>
<p><input name=file type=file accept=".zip,.xml" required></p>
<p><button>Upload</button></p></form>
<p>Progress: <a href=/ingest/apple-export/status>/ingest/apple-export/status</a></p>"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    html = f"<!doctype html><meta name=viewport content='width=device-width'><h2>{title}</h2>{body}"
    return HTMLResponse(html, status_code=status)


def process_export(path: str, since: date) -> None:
    """Parse the export, store samples in batches, then rebuild every touched day."""
    stats = ExportStats()
    STATE.update(status="parsing", started_at=time.time(), since=since.isoformat(), error=None)
    try:
        days: set[date] = set()
        with open_export_xml(path) as stream, SessionLocal() as session:
            batch = []
            for sample in iter_samples(stream, since, stats):
                batch.append(sample)
                days.add(sample.day)
                if len(batch) >= 5000:
                    store_samples(session, batch)
                    session.commit()
                    batch.clear()
                    STATE.update(records_seen=stats.records_seen, samples=stats.samples)
            store_samples(session, batch)
            session.commit()
            STATE.update(status="computing days", days=len(days), samples=stats.samples)
            ordered = sorted(days)
            for i in range(0, len(ordered), 50):
                recompute_days(session, ordered[i : i + 50])
                session.commit()
                STATE["days_done"] = min(i + 50, len(ordered))
        STATE["status"] = "computing scores"
        recompute_all(SessionLocal)
        STATE.update(
            status="done",
            records_seen=stats.records_seen,
            samples=stats.samples,
            skipped=stats.skipped,
            by_metric=dict(stats.by_metric),
            first_day=ordered[0].isoformat() if ordered else None,
            last_day=ordered[-1].isoformat() if ordered else None,
        )
    except Exception as err:  # noqa: BLE001  (report it on the status page)
        log.exception("Apple Health import failed")
        STATE.update(status="failed", error=f"{type(err).__name__}: {err}"[:500])
    finally:
        os.unlink(path)
        _lock.release()


def start_import(path: str, since: date) -> None:
    threading.Thread(target=process_export, args=(path, since), daemon=True).start()


@router.get("")
def form() -> HTMLResponse:
    return HTMLResponse(FORM)


@router.post("")
def upload(
    secret: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    expected = get_settings().ingest_secret
    if not expected:
        return _page("Not configured", "<p>INGEST_SECRET is not set.</p>", 503)
    if not hmac.compare_digest(secret, expected):
        return _page("Wrong secret", "<p>Use the INGEST_SECRET from Railway.</p>", 401)
    if not _lock.acquire(blocking=False):
        return _page(
            "Already importing", "<p>See <a href=/ingest/apple-export/status>status</a>.</p>", 409
        )
    try:
        fd, path = tempfile.mkstemp(suffix=".zip")
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(file.file, out, length=1 << 20)
    except Exception:
        _lock.release()
        raise
    since = date.today() - timedelta(days=get_settings().apple_export_days)
    STATE.clear()
    STATE.update(status="queued", uploaded_bytes=os.path.getsize(path))
    start_import(path, since)
    return _page(
        "Upload received ✅",
        f"<p>Importing everything since {since.isoformat()}. This takes a few minutes.</p>"
        "<p>Progress: <a href=/ingest/apple-export/status>/ingest/apple-export/status</a></p>",
    )


@router.get("/status")
def status() -> dict:
    return dict(STATE)
