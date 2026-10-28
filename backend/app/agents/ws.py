"""GET /ws/events: the event bus, streamed to the office page.

On connect the page gets the last events (so it can show the latest state at once), then
every new event as it happens, plus a ping every 25 s so proxies keep the socket open.

The bubbles carry the owner's health numbers, so the live feed needs OFFICE_VIEW_KEY
(``?key=...``); without it the socket closes (code 4401) and the page offers its demo instead.
"""

import asyncio
import hmac
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.events import Event, bus
from app.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter()
RECENT = 30
PING_EVERY_S = 25
QUEUE_MAX = 500


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket, key: str = "") -> None:
    expected = get_settings().office_view_key
    if not expected or not hmac.compare_digest(key.encode(), expected.encode()):
        # Accept, then close: a socket closed before it's accepted reaches the browser as a
        # failed handshake (code 1006) behind Railway's proxy, so the page would retry forever
        # instead of seeing 4401 and showing the demo.
        await websocket.accept()
        await websocket.close(code=4401)
        return
    await websocket.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_MAX)

    def put(event: Event) -> None:
        if not queue.full():  # a stalled page drops events instead of growing memory
            queue.put_nowait(event)

    # Agents run in worker threads; hand their events over to this socket's event loop.
    unsubscribe = bus.subscribe(lambda e: loop.call_soon_threadsafe(put, e))
    try:
        await websocket.send_json(
            {"type": "hello", "recent": [e.as_dict() for e in bus.recent()[-RECENT:]]}
        )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), PING_EVERY_S)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json({"type": "event", "event": event.as_dict()})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        unsubscribe()
