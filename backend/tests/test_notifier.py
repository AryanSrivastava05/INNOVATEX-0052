import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import httpx

from app.alerts import AlertManager
from app.config import settings
from app.events import EventHub
from app.models import Alert, Patient, Reading
from app.notifier import send_alert
from app.store import InMemoryRepository


def critical_alert() -> Alert:
    now = datetime.now(timezone.utc)
    return Alert(
        id="alert-1",
        patient_id="P001",
        type="heart_rate_high",
        metric="heart_rate",
        observed=135,
        threshold=130,
        severity="critical",
        kind="threshold",
        explanation="Illustrative threshold breach",
        evidence=[],
        status="active",
        created_at=now,
        updated_at=now,
        occurrences=1,
    )


def test_notifier_is_noop_without_webhook(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "")
    asyncio.run(send_alert(critical_alert()))


def test_notifier_posts_simulated_alert_with_three_second_timeout(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://example.test/hook")
    response = Mock()
    response.raise_for_status = Mock()
    client = AsyncMock()
    client.post.return_value = response

    class ClientContext:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 3.0

        async def __aenter__(self):
            return client

        async def __aexit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.notifier.httpx.AsyncClient", ClientContext)
    alert = critical_alert()

    asyncio.run(send_alert(alert))

    client.post.assert_awaited_once()
    posted = client.post.await_args
    assert posted.args == ("https://example.test/hook",)
    assert posted.kwargs["json"]["patient_id"] == "P001"
    assert posted.kwargs["json"]["simulated"] is True


def test_notifier_failure_is_logged_and_does_not_raise(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://example.test/hook")
    client = AsyncMock()
    client.post.side_effect = httpx.ConnectError("synthetic network failure")

    class ClientContext:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self):
            return client

        async def __aexit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.notifier.httpx.AsyncClient", ClientContext)

    asyncio.run(send_alert(critical_alert()))

    assert "Alert webhook delivery failed" in caplog.text


def test_new_critical_alert_schedules_background_webhook(monkeypatch) -> None:
    async def run_test() -> None:
        notified = asyncio.Event()

        async def notify(_alert: Alert) -> None:
            notified.set()

        send_mock = AsyncMock(side_effect=notify)
        monkeypatch.setattr("app.notifier.send_alert", send_mock)
        repository = InMemoryRepository()
        repository.add_patient(Patient(id="P001", name="Synthetic Patient", age=50))
        event_hub = EventHub(repository)
        manager = AlertManager(repository)
        manager.event_hub = event_hub
        reading = Reading(
            patient_id="P001",
            ts=datetime.now(timezone.utc),
            hr=135,
            sys_bp=120,
            dia_bp=80,
            spo2=97,
            quality="ok",
        )
        repository.add_reading(reading)

        manager.process_tick([reading])
        await asyncio.wait_for(notified.wait(), timeout=1)

        send_mock.assert_awaited_once()
        assert send_mock.await_args.args[0].severity == "critical"

    asyncio.run(run_test())


def test_escalation_schedules_webhook(monkeypatch) -> None:
    async def run_test() -> None:
        notified = asyncio.Event()

        async def notify(_alert: Alert) -> None:
            notified.set()

        send_mock = AsyncMock(side_effect=notify)
        monkeypatch.setattr("app.notifier.send_alert", send_mock)
        monkeypatch.setattr(settings, "escalation_seconds", 1)
        repository = InMemoryRepository()
        repository.add_patient(Patient(id="P001", name="Synthetic Patient", age=50))
        event_hub = EventHub(repository)
        manager = AlertManager(repository)
        manager.event_hub = event_hub
        alert = critical_alert()
        repository.add_alert(alert)

        escalated = manager.escalate_overdue(
            now=alert.created_at + timedelta(seconds=2)
        )
        await asyncio.wait_for(notified.wait(), timeout=1)

        assert len(escalated) == 1
        send_mock.assert_awaited_once()
        assert send_mock.await_args.args[0].status == "escalated"

    asyncio.run(run_test())
