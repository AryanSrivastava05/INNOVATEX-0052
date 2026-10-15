from datetime import datetime, timedelta, timezone

from app.alerts import AlertManager
from app.handoff import generate_handoff
from app.models import Alert, Patient, Reading
from app.store import InMemoryRepository


def test_handoff_has_windowed_sbar_sections_and_disclaimer() -> None:
    repository = InMemoryRepository()
    now = datetime.now(timezone.utc)
    repository.add_patient(Patient(id="P001", name="Synthetic Avery", age=50))
    reading = Reading(
        patient_id="P001",
        ts=now,
        hr=135,
        sys_bp=120,
        dia_bp=80,
        spo2=97,
        quality="ok",
    )
    repository.add_reading(reading)
    alert = Alert(
        id="active-1",
        patient_id="P001",
        type="heart_rate_high",
        metric="heart_rate",
        observed=135,
        threshold=130,
        severity="critical",
        kind="threshold",
        explanation="Illustrative threshold breach",
        evidence=[reading],
        status="active",
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=2),
        occurrences=2,
    )
    old_alert = alert.model_copy(
        update={
            "id": "old-1",
            "created_at": now - timedelta(hours=2),
            "updated_at": now - timedelta(hours=2),
            "status": "resolved",
        }
    )
    repository.add_alert(alert)
    repository.add_alert(old_alert)

    handoff = generate_handoff(
        repository,
        window_minutes=60,
        now=now,
        consecutive_abnormal={("P001", "heart_rate"): 3},
    )

    assert handoff.simulated is True
    assert handoff.generated_at == now
    assert [item.id for item in handoff.new_alerts] == ["active-1"]
    assert [item.id for item in handoff.worsening] == ["active-1"]
    assert handoff.resolved == []
    assert [item.id for item in handoff.unacknowledged] == ["active-1"]
    assert all(
        section in handoff.text
        for section in ("Situation:", "Background:", "Assessment:", "Review needed:")
    )
    assert "Decision support only. Not a diagnosis." in handoff.text
