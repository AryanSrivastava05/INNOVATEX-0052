from datetime import datetime, timedelta, timezone

import pytest

from app.models import Reading
from app.rules import demo_thresholds, evaluate_reading

NOW = datetime.now(timezone.utc)


def reading(
    *,
    spo2: int | None = 97,
    hr: int | None = 70,
    sys_bp: int | None = 120,
    quality: str = "ok",
    ts: datetime = NOW,
) -> Reading:
    return Reading(
        patient_id="P001",
        ts=ts,
        hr=hr,
        sys_bp=sys_bp,
        dia_bp=80,
        spo2=spo2,
        quality=quality,
    )


@pytest.mark.parametrize(
    ("spo2", "expected_severity"),
    [(92, None), (91, "warning"), (90, "warning"), (89, "critical")],
)
def test_spo2_threshold_boundaries(
    spo2: int,
    expected_severity: str | None,
) -> None:
    result = evaluate_reading(reading(spo2=spo2), [], now=NOW)
    matches = [finding for finding in result.findings if finding.type == "spo2_low"]

    assert ([finding.severity for finding in matches] or [None]) == [expected_severity]


@pytest.mark.parametrize(
    ("hr", "expected_type", "expected_severity"),
    [
        (110, None, None),
        (111, "heart_rate_high", "warning"),
        (130, "heart_rate_high", "warning"),
        (131, "heart_rate_high", "critical"),
        (50, None, None),
        (49, "heart_rate_low", "warning"),
        (40, "heart_rate_low", "warning"),
        (39, "heart_rate_low", "critical"),
    ],
)
def test_heart_rate_threshold_boundaries(
    hr: int,
    expected_type: str | None,
    expected_severity: str | None,
) -> None:
    result = evaluate_reading(reading(hr=hr), [], now=NOW)
    matches = [finding for finding in result.findings if finding.metric == "heart_rate"]

    assert (
        (matches[0].type, matches[0].severity) if matches else (None, None)
    ) == (expected_type, expected_severity)


@pytest.mark.parametrize(
    ("sys_bp", "expected_type", "expected_severity"),
    [
        (160, None, None),
        (161, "systolic_bp_high", "warning"),
        (180, "systolic_bp_high", "warning"),
        (181, "systolic_bp_high", "critical"),
        (95, None, None),
        (94, "systolic_bp_low", "warning"),
        (85, "systolic_bp_low", "warning"),
        (84, "systolic_bp_low", "critical"),
    ],
)
def test_systolic_bp_threshold_boundaries(
    sys_bp: int,
    expected_type: str | None,
    expected_severity: str | None,
) -> None:
    result = evaluate_reading(reading(sys_bp=sys_bp), [], now=NOW)
    matches = [finding for finding in result.findings if finding.metric == "systolic_bp"]

    assert (
        (matches[0].type, matches[0].severity) if matches else (None, None)
    ) == (expected_type, expected_severity)


def test_signal_lost_for_missing_or_stale_reading() -> None:
    missing = evaluate_reading(reading(quality="missing"), [], now=NOW)
    stale_quality = evaluate_reading(reading(quality="stale"), [], now=NOW)
    stale = evaluate_reading(
        reading(ts=NOW - timedelta(seconds=demo_thresholds()["spo2"]["warning_below"])),
        [],
        now=NOW,
    )

    assert any(finding.type == "signal_lost" for finding in missing.findings)
    assert any(finding.type == "signal_lost" for finding in stale_quality.findings)
    assert any(finding.type == "signal_lost" for finding in stale.findings)


def test_three_consecutive_abnormal_readings_raise_persistence_severity() -> None:
    previous = [reading(spo2=91), reading(spo2=90)]
    result = evaluate_reading(reading(spo2=91), previous, now=NOW)

    finding = next(finding for finding in result.findings if finding.type == "spo2_low")
    assert finding.severity == "critical"
    assert result.consecutive_abnormal["spo2"] == 3


def test_nonconsecutive_abnormal_readings_do_not_raise_persistence_severity() -> None:
    previous = [reading(spo2=91), reading(spo2=97)]
    result = evaluate_reading(reading(spo2=91), previous, now=NOW)

    finding = next(finding for finding in result.findings if finding.type == "spo2_low")
    assert finding.severity == "warning"
    assert result.consecutive_abnormal["spo2"] == 1
