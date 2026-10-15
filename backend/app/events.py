import asyncio
import json
from datetime import datetime, timezone

from app.models import AuditEntry
from app.store import Repository


class EventHub:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.loop = asyncio.get_running_loop()
        self._subscribers: set[asyncio.Queue[str]] = set()

    def publish(
        self,
        event: str,
        details: dict[str, object],
        *,
        stream_event: str | None = None,
    ) -> None:
        entry = AuditEntry(
            ts=datetime.now(timezone.utc),
            event=event,
            details=details,
        )
        self.repository.add_audit_entry(entry)
        stream_event = stream_event or event
        if stream_event in {"tick", "alert", "ranking"}:
            message = json.dumps(details, separators=(",", ":"))
            self.loop.call_soon_threadsafe(self._deliver, stream_event, message)

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def _deliver(self, event: str, message: str) -> None:
        formatted = f"event: {event}\ndata: {message}\n\n"
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(formatted)
