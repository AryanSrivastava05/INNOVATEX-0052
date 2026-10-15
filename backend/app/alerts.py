import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config import settings
from app.events import EventHub
from app.models import Alert, Reading
from app.rules import RuleFinding, evaluate_reading, is_normal_for_finding
from app.events import EventHub
from app.store import Repository


class AlertManager:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.event_hub: EventHub | None = None
        self._alert_started_at: dict[str, datetime] = {}
        self._normal_counts: dict[tuple[str, str], int] = {}
        self.consecutive_abnormal: dict[tuple[str, str], int] = {}

    def process_tick(self, readings: list[Reading]) -> list[Alert]:
        changed: list[Alert] = []
        for reading in readings:
            history = self.repository.get_readings(reading.patient_id)
            evaluation = evaluate_reading(reading, history[:-1] if history else [])
            for metric, count in evaluation.consecutive_abnormal.items():
                self.consecutive_abnormal[(reading.patient_id, metric)] = count
            changed.extend(self.process_reading(reading, evaluation.findings))
        changed.extend(self.escalate_overdue())
        return changed

    def process_reading(
        self,
        reading: Reading,
        findings: list[RuleFinding] | None = None,
    ) -> list[Alert]:
        history = self.repository.get_readings(reading.patient_id)
        if findings is None:
            findings = evaluate_reading(
                reading,
                history[:-1] if history else [],
            ).findings

        now = datetime.now(timezone.utc)
        by_type = {finding.type: finding for finding in findings}
        changed: list[Alert] = []

        for finding in findings:
            alert = next(
                (
                    existing
                    for existing in self.repository.get_alerts(reading.patient_id)
                    if existing.type == finding.type and existing.status != "resolved"
                ),
                None,
            )
            if alert is None:
                alert = Alert(
                    id=str(uuid4()),
                    patient_id=reading.patient_id,
                    type=finding.type,
                    metric=finding.metric,
                    observed=finding.observed,
                    threshold=finding.threshold,
                    severity=finding.severity,
                    kind=finding.kind,
                    explanation=finding.explanation,
                    evidence=[reading],
                    status="active",
                    created_at=now,
                    updated_at=now,
                    occurrences=1,
                )
                self.repository.add_alert(alert)
                self._alert_started_at[alert.id] = now
                if self.event_hub is not None:
                    self.event_hub.publish(
                        "alert_create",
                        {
                            "alert_id": alert.id,
                            "patient_id": alert.patient_id,
                            "type": alert.type,
                            "severity": alert.severity,
                        },
                        stream_event="alert",
                    )
                if alert.severity == "critical":
                    self._notify(alert)
            else:
                previous_severity = alert.severity
                reopened = alert.status == "acknowledged"
                alert = alert.model_copy(
                    update={
                        "observed": finding.observed,
                        "threshold": finding.threshold,
                        "severity": finding.severity,
                        "explanation": (
                            f"{finding.explanation} Reopened."
                            if reopened
                            else finding.explanation
                        ),
                        "evidence": [*alert.evidence, reading],
                        "status": "active" if reopened else alert.status,
                        "ack_note": "reopened" if reopened else alert.ack_note,
                        "updated_at": now,
                        "occurrences": alert.occurrences + 1,
                    }
                )
                if reopened:
                    self._alert_started_at[alert.id] = now
                self.repository.update_alert(alert)
                if self.event_hub is not None:
                    self.event_hub.publish(
                        "alert_update",
                        {
                            "alert_id": alert.id,
                            "patient_id": alert.patient_id,
                            "type": alert.type,
                            "status": alert.status,
                            "severity": alert.severity,
                            "reopened": reopened,
                        },
                        stream_event="alert",
                    )
                if (
                    alert.severity == "critical"
                    and previous_severity != "critical"
                ):
                    self._notify(alert)
            self._normal_counts[(reading.patient_id, finding.type)] = 0
            changed.append(alert)

        for alert in self.repository.get_alerts(reading.patient_id):
            if alert.status == "resolved" or alert.type in by_type:
                continue
            counter_key = (reading.patient_id, alert.type)
            if is_normal_for_finding(alert.type, reading):
                count = self._normal_counts.get(counter_key, 0) + 1
                self._normal_counts[counter_key] = count
                if count >= 3:
                    resolved = alert.model_copy(
                        update={"status": "resolved", "updated_at": now}
                    )
                    self.repository.update_alert(resolved)
                    changed.append(resolved)
                    self._audit_alert_update(resolved)
            else:
                self._normal_counts[counter_key] = 0

        return changed

    def escalate_overdue(
        self,
        *,
        now: datetime | None = None,
    ) -> list[Alert]:
        current_time = now or datetime.now(timezone.utc)
        escalation_after = timedelta(seconds=settings.escalation_seconds)
        escalated_alerts: list[Alert] = []
        for alert in self.repository.get_alerts():
            if (
                alert.status != "active"
                or alert.severity != "critical"
                or current_time - self._alert_started_at.get(alert.id, alert.created_at)
                < escalation_after
            ):
                continue
            escalated = alert.model_copy(
                update={"status": "escalated", "updated_at": current_time}
            )
            self.repository.update_alert(escalated)
            escalated_alerts.append(escalated)
            self._audit_alert_update(escalated, escalation=True)
            self._notify(escalated)
        return escalated_alerts

    def acknowledge(self, alert_id: str, note: str | None = None) -> Alert | None:
        alert = self.repository.get_alert(alert_id)
        if alert is None or alert.status == "resolved":
            return None
        acknowledged = alert.model_copy(
            update={
                "status": "acknowledged",
                "acknowledged_at": datetime.now(timezone.utc),
                "ack_note": note,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.repository.update_alert(acknowledged)
        self._alert_started_at.pop(alert.id, None)
        if self.event_hub is not None:
            self.event_hub.publish(
                "alert_acknowledged",
                {
                    "alert_id": acknowledged.id,
                    "patient_id": acknowledged.patient_id,
                    "note": acknowledged.ack_note,
                },
            )
        return acknowledged

    def list_alerts(self, status: str) -> list[Alert]:
        alerts = [
            alert for alert in self.repository.get_alerts() if alert.status == status
        ]
        return sorted(alerts, key=lambda alert: alert.created_at)

    def _audit_alert_update(
        self,
        alert: Alert,
        *,
        escalation: bool = False,
    ) -> None:
        if self.event_hub is not None:
            self.event_hub.publish(
                "alert_update",
                {
                    "alert_id": alert.id,
                    "patient_id": alert.patient_id,
                    "type": alert.type,
                    "status": alert.status,
                    "escalated": escalation,
                },
                stream_event="alert",
            )

    def _notify(self, alert: Alert) -> None:
        if self.event_hub is not None and self.event_hub.loop.is_running():
            from app.notifier import send_alert

            self.event_hub.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(send_alert(alert))
            )
