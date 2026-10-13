"""The event bus: every agent step becomes an event, and the office animates from them.

An event is ``{agent, status, target, text}`` (see CLAUDE.md):

    agent    "manager" | "health_coach" | "market_scout"
    status   idle | thinking | walking | working | talking
    target   who or what it's directed at: another agent, a tool name, or "owner"
    text     a short human-readable line (speech-bubble text for "talking")

The bus keeps the latest events in memory and hands each one to every subscriber. Phase 5's
``/ws/events`` WebSocket subscribes to it; tests read ``recent()``.
"""

import itertools
import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

log = logging.getLogger(__name__)

STATUSES = {"idle", "thinking", "walking", "working", "talking"}
AGENTS = {"manager", "health_coach", "market_scout"}
TEXT_LIMIT = 280


@dataclass(frozen=True)
class Event:
    agent: str
    status: str
    target: str | None = None
    text: str = ""
    id: int = 0
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    run_id: str | None = None  # groups the events of one request

    def as_dict(self) -> dict:
        return asdict(self)


class EventBus:
    def __init__(self, keep: int = 500) -> None:
        self._events: deque[Event] = deque(maxlen=keep)
        self._subscribers: list[Callable[[Event], None]] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def emit(
        self,
        agent: str,
        status: str,
        target: str | None = None,
        text: str = "",
        run_id: str | None = None,
    ) -> Event:
        if agent not in AGENTS:
            raise ValueError(f"unknown agent {agent!r}")
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        if len(text) > TEXT_LIMIT:
            text = text[: TEXT_LIMIT - 1] + "…"
        with self._lock:
            event = Event(agent, status, target, text, next(self._ids), run_id=run_id)
            self._events.append(event)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # a broken subscriber never stops an agent
                log.exception("Event subscriber failed")
        return event

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        """Call ``callback`` with every new event. Returns a function that unsubscribes."""
        with self._lock:
            self._subscribers.append(callback)
        return lambda: self._unsubscribe(callback)

    def _unsubscribe(self, callback: Callable[[Event], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def recent(self, run_id: str | None = None) -> list[Event]:
        with self._lock:
            events = list(self._events)
        return [e for e in events if run_id is None or e.run_id == run_id]


bus = EventBus()
