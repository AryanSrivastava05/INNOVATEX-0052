from datetime import datetime, timedelta, timezone

from app.models import HandoffResponse, PatientStatus
from app.scoring import calculate_score
from app.store import Repository


def generate_handoff(
    repository: Repository,
    *,
    window_minutes: int = 60,
    now: datetime | None = None,
    consecutive_abnormal: dict[tuple[str, str], int] | None = None,
) -> HandoffResponse:
    generated_at = now or datetime.now(timezone.utc)
    window_start = generated_at - timedelta(minutes=window_minutes)
    alerts = repository.get_alerts()
    new_alerts = [
        alert for alert in alerts if alert.created_at >= window_start
    ]
    worsening = [
        alert
        for alert in alerts
        if alert.updated_at >= window_start
        and alert.occurrences > 1
        and alert.status in ("active", "escalated")
    ]
    resolved = [
        alert
        for alert in alerts
        if alert.status == "resolved" and alert.updated_at >= window_start
    ]
    unacknowledged = [
        alert for alert in alerts if alert.status in ("active", "escalated")
    ]

    patient_statuses: list[PatientStatus] = []
    for patient in repository.get_patients():
        patient_alerts = repository.get_alerts(patient.id)
        counts = {
            metric: count
            for (patient_id, metric), count in (consecutive_abnormal or {}).items()
            if patient_id == patient.id
        }
        score = calculate_score(patient_alerts, counts)
        patient_statuses.append(
            PatientStatus(
                patient=patient,
                latest=repository.get_latest_reading(patient.id),
                risk_band=score.risk_band,
                score=score.score,
                score_breakdown=score.score_breakdown,
                active_alert_count=sum(
                    alert.status in ("active", "escalated")
                    for alert in patient_alerts
                ),
                data_freshness_seconds=0,
            )
        )
    high_risk = [
        item for item in patient_statuses if item.risk_band == "High"
    ]
    text_lines = [
        "Situation: "
        f"{len(unacknowledged)} unacknowledged alert(s), "
        f"{len(new_alerts)} new alert(s) in the last {window_minutes} minutes.",
        "Background: "
        + (
            "; ".join(
                f"{item.patient.name} ({item.patient.id}) has score {item.score}: "
                + ", ".join(entry.reason for entry in item.score_breakdown)
                for item in high_risk
            )
            if high_risk
            else "No patients are currently in the High prioritization band."
        ),
        "Assessment: "
        + (
            "; ".join(
                f"{item.type} for {item.patient_id} updated "
                f"{item.occurrences} time(s)"
                for item in worsening
            )
            if worsening
            else "No active alert has worsened in this window."
        ),
        "Review needed: "
        + (
            "; ".join(
                f"{alert.patient_id} {alert.type} ({alert.severity}, "
                f"{alert.status})"
                for alert in unacknowledged
            )
            if unacknowledged
            else "No unacknowledged alerts."
        ),
        "Decision support only. Not a diagnosis.",
    ]

    return HandoffResponse(
        generated_at=generated_at,
        new_alerts=new_alerts,
        worsening=worsening,
        resolved=resolved,
        unacknowledged=unacknowledged,
        text="\n".join(text_lines),
    )
