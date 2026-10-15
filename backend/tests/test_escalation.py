from datetime import datetime, timedelta, timezone

from app.alerts import AlertManager
from app.config import settings
from app.models import Alert, Patient
from app.scoring import calculate_score
from app.store import InMemoryRepository


def create_critical_alert(created_at: datetime) -> Alert:
    return Alert(
        id="critical-alert",
        patient_id="P099",
        type="heart_rate_high",
        metric="heart_rate",
        observed=135,
        threshold=130,
        severity="critical",
        kind="threshold",
        explanation="Illustrative critical threshold crossed.",
        evidence=[],
        status="active",
        created_at=created_at,
        updated_at=created_at,
        occurrences=1,
    )


def create_manager(alert: Alert) -> tuple[InMemoryRepository, AlertManager]:
    repository = InMemoryRepository()
    repository.add_patient(Patient(id="P099", name="Synthetic Patient", age=50))
    repository.add_alert(alert)
    return repository, AlertManager(repository)


def test_unacknowledged_critical_escalates_after_configured_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "escalation_seconds", 60)
    created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    alert = create_critical_alert(created_at)
    repository, manager = create_manager(alert)

    escalated = manager.escalate_overdue(now=datetime.now(timezone.utc))

    assert len(escalated) == 1
    assert escalated[0].id == alert.id
    assert escalated[0].status == "escalated"
    assert calculate_score([escalated[0]]).score == 55
    assert calculate_score([escalated[0]]).score_breakdown[-1].factor == "escalation"
    assert repository.get_alert(alert.id).status == "escalated"


def test_escalation_waits_until_timeout_and_only_runs_once(monkeypatch) -> None:
    monkeypatch.setattr(settings, "escalation_seconds", 60)
    created_at = datetime.now(timezone.utc)
    alert = create_critical_alert(created_at)
    _, manager = create_manager(alert)

    before_timeout = manager.escalate_overdue(
        now=created_at + timedelta(seconds=59)
    )
    after_timeout = manager.escalate_overdue(
        now=created_at + timedelta(seconds=60)
    )
    subsequent = manager.escalate_overdue(
        now=created_at + timedelta(seconds=120)
    )

    assert before_timeout == []
    assert len(after_timeout) == 1
    assert subsequent == []


def test_acknowledged_critical_alert_does_not_escalate(monkeypatch) -> None:
    monkeypatch.setattr(settings, "escalation_seconds", 1)
    created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    alert = create_critical_alert(created_at)
    _, manager = create_manager(alert)
    manager.acknowledge(alert.id)

    assert manager.escalate_overdue(now=datetime.now(timezone.utc)) == []
