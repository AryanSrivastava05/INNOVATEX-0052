from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import Alert, PatientStatus, ScoreBreakdownItem


@dataclass(frozen=True)
class ScoreResult:
    score: int
    risk_band: str
    score_breakdown: list[ScoreBreakdownItem]


def calculate_score(
    alerts: list[Alert],
    consecutive_abnormal: dict[str, int] | None = None,
) -> ScoreResult:
    current_alerts = [
        alert for alert in alerts if alert.status in ("active", "escalated")
    ]
    breakdown: list[ScoreBreakdownItem] = []

    critical_count = sum(alert.severity == "critical" for alert in current_alerts)
    warning_count = sum(alert.severity == "warning" for alert in current_alerts)
    severity_points = critical_count * 40 + warning_count * 20
    if severity_points:
        reasons = []
        if critical_count:
            reasons.append(f"{critical_count} critical active alert(s) × 40")
        if warning_count:
            reasons.append(f"{warning_count} warning active alert(s) × 20")
        breakdown.append(
            ScoreBreakdownItem(
                factor="severity",
                points=severity_points,
                reason="; ".join(reasons),
            )
        )

    abnormal_counts = {
        metric: count
        for metric, count in (consecutive_abnormal or {}).items()
        if count > 0
    }
    persistence_points = min(15, sum(abnormal_counts.values()) * 3)
    if persistence_points:
        count_summary = ", ".join(
            f"{metric}: {count}" for metric, count in sorted(abnormal_counts.items())
        )
        breakdown.append(
            ScoreBreakdownItem(
                factor="persistence",
                points=persistence_points,
                reason=(
                    f"{count_summary} consecutive abnormal reading(s), "
                    "3 points each, capped at 15"
                ),
            )
        )

    trend_count = sum(alert.kind == "trend" for alert in current_alerts)
    if trend_count:
        breakdown.append(
            ScoreBreakdownItem(
                factor="trend",
                points=15,
                reason=f"{trend_count} active trend alert(s)",
            )
        )

    signal_count = sum(alert.type == "signal_lost" for alert in current_alerts)
    if signal_count:
        breakdown.append(
            ScoreBreakdownItem(
                factor="signal",
                points=10,
                reason=f"{signal_count} active signal_lost alert(s)",
            )
        )

    if any(alert.status == "escalated" for alert in current_alerts):
        breakdown.append(
            ScoreBreakdownItem(
                factor="escalation",
                points=15,
                reason="At least one alert is escalated",
            )
        )

    advisory_count = sum(alert.kind == "advisory" for alert in current_alerts)
    if advisory_count:
        breakdown.append(
            ScoreBreakdownItem(
                factor="advisory",
                points=5,
                reason=f"{advisory_count} active baseline advisory alert(s)",
            )
        )

    score = sum(item.points for item in breakdown)
    risk_band = "High" if score >= 50 else "Medium" if score >= 20 else "Routine"
    return ScoreResult(score, risk_band, breakdown)


def sort_patients_by_priority(
    patients: list[PatientStatus],
    alerts: list[Alert],
) -> list[PatientStatus]:
    oldest_unacknowledged: dict[str, datetime] = {}
    for alert in alerts:
        if alert.status not in ("active", "escalated"):
            continue
        current = oldest_unacknowledged.get(alert.patient_id)
        if current is None or alert.created_at < current:
            oldest_unacknowledged[alert.patient_id] = alert.created_at

    return sorted(
        patients,
        key=lambda patient: (
            -patient.score,
            oldest_unacknowledged.get(patient.patient.id, datetime.max.replace(tzinfo=timezone.utc)),
            patient.patient.id,
        ),
    )


def sort_alerts_by_priority(
    alerts: list[Alert],
    patient_scores: dict[str, int],
    all_alerts: list[Alert],
) -> list[Alert]:
    oldest_unacknowledged: dict[str, datetime] = {}
    for alert in all_alerts:
        if alert.status not in ("active", "escalated"):
            continue
        current = oldest_unacknowledged.get(alert.patient_id)
        if current is None or alert.created_at < current:
            oldest_unacknowledged[alert.patient_id] = alert.created_at

    return sorted(
        alerts,
        key=lambda alert: (
            -patient_scores.get(alert.patient_id, 0),
            oldest_unacknowledged.get(
                alert.patient_id,
                datetime.max.replace(tzinfo=timezone.utc),
            ),
            alert.created_at,
            alert.id,
        ),
    )
