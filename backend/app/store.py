from collections import deque
from typing import Protocol

from app.models import Alert, AuditEntry, Patient, Reading


class Repository(Protocol):
    def add_patient(self, patient: Patient) -> None: ...

    def add_reading(self, reading: Reading) -> None: ...

    def get_patient(self, patient_id: str) -> Patient | None: ...

    def get_patients(self) -> list[Patient]: ...

    def get_latest_reading(self, patient_id: str) -> Reading | None: ...

    def get_readings(self, patient_id: str, limit: int | None = None) -> list[Reading]: ...

    def add_alert(self, alert: Alert) -> None: ...

    def get_alert(self, alert_id: str) -> Alert | None: ...

    def get_alerts(self, patient_id: str | None = None) -> list[Alert]: ...

    def update_alert(self, alert: Alert) -> None: ...

    def add_audit_entry(self, entry: AuditEntry) -> None: ...

    def get_audit_entries(self, limit: int) -> list[AuditEntry]: ...


class InMemoryRepository:
    def __init__(self) -> None:
        self._patients: dict[str, Patient] = {}
        self._readings: dict[str, deque[Reading]] = {}
        self._alerts: dict[str, Alert] = {}
        self._audit_entries: deque[AuditEntry] = deque(maxlen=1000)

    def add_patient(self, patient: Patient) -> None:
        self._patients[patient.id] = patient
        self._readings.setdefault(patient.id, deque())

    def add_reading(self, reading: Reading) -> None:
        if reading.patient_id not in self._patients:
            raise KeyError(f"Unknown patient: {reading.patient_id}")
        self._readings[reading.patient_id].append(reading)

    def get_patient(self, patient_id: str) -> Patient | None:
        return self._patients.get(patient_id)

    def get_patients(self) -> list[Patient]:
        return list(self._patients.values())

    def get_latest_reading(self, patient_id: str) -> Reading | None:
        readings = self._readings.get(patient_id)
        return readings[-1] if readings else None

    def get_readings(self, patient_id: str, limit: int | None = None) -> list[Reading]:
        readings = list(self._readings.get(patient_id, ()))
        return readings if limit is None else readings[-limit:]

    def add_alert(self, alert: Alert) -> None:
        self._alerts[alert.id] = alert

    def get_alert(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    def get_alerts(self, patient_id: str | None = None) -> list[Alert]:
        alerts = list(self._alerts.values())
        if patient_id is not None:
            alerts = [alert for alert in alerts if alert.patient_id == patient_id]
        return alerts

    def update_alert(self, alert: Alert) -> None:
        if alert.id not in self._alerts:
            raise KeyError(f"Unknown alert: {alert.id}")
        self._alerts[alert.id] = alert

    def add_audit_entry(self, entry: AuditEntry) -> None:
        self._audit_entries.append(entry)

    def get_audit_entries(self, limit: int) -> list[AuditEntry]:
        return list(self._audit_entries)[-limit:]
