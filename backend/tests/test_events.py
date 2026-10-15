import asyncio
from datetime import datetime, timezone

from app.events import EventHub
from app.store import InMemoryRepository


def test_event_hub_audits_and_broadcasts_sse_events() -> None:
    async def run_test() -> None:
        repository = InMemoryRepository()
        event_hub = EventHub(repository)
        queue = event_hub.subscribe()
        event_hub.publish("tick", {"tick": 4, "simulated": True})
        event_hub.publish(
            "alert_create",
            {"alert_id": "a1", "simulated": True},
            stream_event="alert",
        )
        event_hub.publish("ranking", {"patients": [], "simulated": True})

        messages = [
            await asyncio.wait_for(queue.get(), timeout=1)
            for _ in range(3)
        ]
        entries = repository.get_audit_entries(10)

        assert messages == [
            'event: tick\ndata: {"tick":4,"simulated":true}\n\n',
            'event: alert\ndata: {"alert_id":"a1","simulated":true}\n\n',
            'event: ranking\ndata: {"patients":[],"simulated":true}\n\n',
        ]
        assert [entry.event for entry in entries] == [
            "tick",
            "alert_create",
            "ranking",
        ]
        assert entries[0].details["tick"] == 4
        assert all(entry.simulated is True for entry in entries)
        assert all(isinstance(entry.ts, datetime) for entry in entries)
        assert all(entry.ts.tzinfo == timezone.utc for entry in entries)

        event_hub.unsubscribe(queue)

    asyncio.run(run_test())
