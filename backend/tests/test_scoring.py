from datetime import datetime, timedelta, timezone

from app.models import Alert, Patient, PatientStatus
from app.scoring import (
    calculate_score,
    sort_alerts_by_priority,
    sort_patients_by_priority,
)

NOW = datetime.now(timezone.utc)


def alert(
    patient_id: str,
    *,
    severity: str = "warning",
    kind: str = "threshold",
    status: str = "active",
    created_at: datetime = NOW,
    alert_id: str = "alert",
    alert_type: str = "spo2_low",
) -> Alert:
    return Alert(
        id=alert_id,
        patient_id=patient_id,
        type=alert_type,
        metric="spo2",
        observed=91,
        threshold=92,
        severity=severity,
        kind=kind,
        explanation="Illustrative test alert",
        evidence=[],
        status=status,
        created_at=created_at,
        updated_at=created_at,
        occurrences=1,
    )


def patient_status(patient_id: str, score: int) -> PatientStatus:
    return PatientStatus(
        patient=Patient(id=patient_id, name=patient_id, age=50),
        latest=None,
        risk_band="High" if score >= 50 else "Medium" if score >= 20 else "Routine",
        score=score,
        score_breakdown=[],
        active_alert_count=0,
        data_freshness_seconds=0,
    )


def test_critical_alert_scores_higher_than_warning_alert() -> None:
    critical = calculate_score([alert("P001", severity="critical")])
    warning = calculate_score([alert("P002", severity="warning")])

    assert critical.score == 40
    assert warning.score == 20
    assert critical.score > warning.score
    assert critical.risk_band == "Medium"
    assert warning.risk_band == "Medium"


def test_score_bands_follow_prd_boundaries() -> None:
    assert calculate_score([]).risk_band == "Routine"
    assert calculate_score([alert("P001")]).risk_band == "Medium"
    assert calculate_score(
        [alert("P001", severity="critical"), alert("P001", severity="warning")]
    ).risk_band == "High"


def test_persistence_and_trend_add_documented_points() -> None:
    result = calculate_score(
        [alert("P001", kind="trend", alert_type="spo2_decline")],
        {"spo2": 3},
    )
    factors = {item.factor: item.points for item in result.score_breakdown}

    assert factors["severity"] == 20
    assert factors["persistence"] == 9
    assert factors["trend"] == 15
    assert result.score == 44
    assert sum(item.points for item in result.score_breakdown) == result.score


def test_persistence_is_capped_at_fifteen_points() -> None:
    result = calculate_score([], {"spo2": 5, "heart_rate": 3})

    persistence = next(item for item in result.score_breakdown if item.factor == "persistence")
    assert persistence.points == 15


def test_escalation_adds_fifteen_points() -> None:
    result = calculate_score(
        [alert("P001", severity="critical", status="escalated")]
    )
    factors = {item.factor: item.points for item in result.score_breakdown}

    assert factors == {"severity": 40, "escalation": 15}
    assert result.score == 55
    assert result.risk_band == "High"


def test_acknowledged_and_resolved_alerts_do_not_add_active_severity() -> None:
    result = calculate_score(
        [
            alert("P001", status="acknowledged"),
            alert("P001", status="resolved", alert_id="resolved"),
        ]
    )

    assert result.score == 0
    assert result.score_breakdown == []


def test_patient_priority_tie_breaks_by_oldest_unacknowledged_alert() -> None:
    earlier = alert(
        "P002",
        created_at=NOW - timedelta(minutes=2),
        alert_id="older",
    )
    later = alert("P001", created_at=NOW, alert_id="newer")

    ordered = sort_patients_by_priority(
        [patient_status("P001", 20), patient_status("P002", 20)],
        [later, earlier],
    )

    assert [patient.patient.id for patient in ordered] == ["P002", "P001"]


def test_alert_priority_tie_breaks_by_oldest_unacknowledged_alert() -> None:
    earlier = alert(
        "P002",
        created_at=NOW - timedelta(minutes=2),
        alert_id="older",
    )
    later = alert("P001", created_at=NOW, alert_id="newer")

    ordered = sort_alerts_by_priority(
        [later, earlier],
        {"P001": 20, "P002": 20},
        [later, earlier],
    )

    assert [item.id for item in ordered] == ["older", "newer"]
