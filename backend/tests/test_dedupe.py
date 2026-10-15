from datetime import datetime, timezone

from app.alerts import AlertManager
from app.models import Patient, Reading
from app.store import InMemoryRepository


def create_reading(*, spo2: int = 91) -> Reading:
    return Reading(
        patient_id="P099",
        ts=datetime.now(timezone.utc),
        hr=70,
        sys_bp=120,
        dia_bp=80,
        spo2=spo2,
        quality="ok",
    )


def create_manager() -> tuple[InMemoryRepository, AlertManager]:
    repository = InMemoryRepository()
    repository.add_patient(Patient(id="P099", name="Synthetic Patient", age=50))
    return repository, AlertManager(repository)


def add_and_process(
    repository: InMemoryRepository,
    manager: AlertManager,
    reading: Reading,
) -> list:
    repository.add_reading(reading)
    return manager.process_tick([reading])


def test_ten_breaching_ticks_create_one_alert_with_ten_occurrences() -> None:
    repository, manager = create_manager()

    for _ in range(10):
        add_and_process(repository, manager, create_reading())

    alerts = repository.get_alerts("P099")
    assert len(alerts) == 1
    assert alerts[0].occurrences == 10


def test_acknowledged_alert_reopens_when_condition_persists() -> None:
    repository, manager = create_manager()
    add_and_process(repository, manager, create_reading())
    alert = repository.get_alerts("P099")[0]
    acknowledged = manager.acknowledge(alert.id, "reviewed")

    assert acknowledged is not None
    assert acknowledged.status == "acknowledged"
    assert acknowledged.ack_note == "reviewed"

    changed = add_and_process(repository, manager, create_reading())
    reopened = repository.get_alert(alert.id)

    assert reopened is not None
    assert len(repository.get_alerts("P099")) == 1
    assert reopened.status == "active"
    assert reopened.ack_note == "reopened"
    assert reopened.occurrences == 2
    assert any("Reopened." in item.explanation for item in changed)


def test_alert_auto_resolves_after_three_consecutive_normal_readings() -> None:
    repository, manager = create_manager()
    add_and_process(repository, manager, create_reading(spo2=91))
    alert = repository.get_alerts("P099")[0]

    for _ in range(3):
        add_and_process(repository, manager, create_reading(spo2=97))

    resolved = repository.get_alert(alert.id)
    assert resolved is not None
    assert resolved.status == "resolved"
