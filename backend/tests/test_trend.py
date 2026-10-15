from datetime import datetime, timezone

from app.models import Reading
from app.rules import evaluate_reading

NOW = datetime.now(timezone.utc)


def readings(values: list[int]) -> list[Reading]:
    return [
        Reading(
            patient_id="P001",
            ts=NOW,
            hr=70,
            sys_bp=120,
            dia_bp=80,
            spo2=value,
            quality="ok",
        )
        for value in values
    ]


def test_declining_spo2_above_low_threshold_triggers_trend() -> None:
    values = readings([98, 97, 96, 95, 94])

    result = evaluate_reading(values[-1], values[:-1], now=NOW)

    finding = next(finding for finding in result.findings if finding.type == "spo2_decline")
    assert finding.severity == "warning"
    assert finding.kind == "trend"
    assert finding.observed == 94


def test_flat_spo2_does_not_trigger_trend() -> None:
    values = readings([97, 97, 97, 97, 97])

    result = evaluate_reading(values[-1], values[:-1], now=NOW)

    assert not any(finding.type == "spo2_decline" for finding in result.findings)


def test_noisy_spo2_does_not_trigger_trend() -> None:
    values = readings([98, 96, 97, 95, 94])

    result = evaluate_reading(values[-1], values[:-1], now=NOW)

    assert not any(finding.type == "spo2_decline" for finding in result.findings)


def test_drop_smaller_than_three_does_not_trigger_trend() -> None:
    values = readings([98, 98, 97, 97, 96])

    result = evaluate_reading(values[-1], values[:-1], now=NOW)

    assert not any(finding.type == "spo2_decline" for finding in result.findings)
