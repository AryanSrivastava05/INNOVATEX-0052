from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.config import settings
from app.models import Reading

Severity = Literal["warning", "critical"]


@dataclass(frozen=True)
class RuleFinding:
    type: str
    metric: str
    observed: int | str
    threshold: int | str
    severity: Severity
    kind: Literal["threshold", "trend", "signal"]
    explanation: str


@dataclass(frozen=True)
class RuleEvaluation:
    findings: list[RuleFinding]
    consecutive_abnormal: dict[str, int]


def demo_thresholds() -> dict[str, dict[str, int]]:
    return {
        "spo2": {
            "warning_below": settings.spo2_warning,
            "critical_below": settings.spo2_critical,
        },
        "heart_rate": {
            "warning_above": settings.heart_rate_warning_high,
            "warning_below": settings.heart_rate_warning_low,
            "critical_above": settings.heart_rate_critical_high,
            "critical_below": settings.heart_rate_critical_low,
        },
        "systolic_bp": {
            "warning_above": settings.systolic_bp_warning_high,
            "warning_below": settings.systolic_bp_warning_low,
            "critical_above": settings.systolic_bp_critical_high,
            "critical_below": settings.systolic_bp_critical_low,
        },
    }


def evaluate_reading(
    reading: Reading,
    history: list[Reading],
    *,
    now: datetime | None = None,
) -> RuleEvaluation:
    findings: list[RuleFinding] = []
    thresholds = demo_thresholds()
    observed_abnormal: dict[str, bool] = {}
    is_fresh = (
        reading.quality == "ok"
        and (now or datetime.now(timezone.utc)) - reading.ts
        <= timedelta(seconds=settings.stale_seconds)
    )

    if not is_fresh:
        findings.append(
            RuleFinding(
                type="signal_lost",
                metric="signal",
                observed=reading.quality,
                threshold=f"fresh within {settings.stale_seconds} seconds",
                severity="warning",
                kind="signal",
                explanation=(
                    f"Latest reading is {reading.quality}; expected a fresh reading "
                    f"within {settings.stale_seconds} seconds."
                ),
            )
        )

    if is_fresh:
        spo2_thresholds = thresholds["spo2"]
        spo2 = reading.spo2
        if spo2 is not None and spo2 < spo2_thresholds["warning_below"]:
            severity: Severity = (
                "critical" if spo2 < spo2_thresholds["critical_below"] else "warning"
            )
            findings.append(
                RuleFinding(
                    type="spo2_low",
                    metric="spo2",
                    observed=spo2,
                    threshold=(
                        spo2_thresholds["critical_below"]
                        if severity == "critical"
                        else spo2_thresholds["warning_below"]
                    ),
                    severity=severity,
                    kind="threshold",
                    explanation=f"SpO2 {spo2} is below the illustrative {severity} threshold.",
                )
            )
        observed_abnormal["spo2"] = spo2 is not None and spo2 < spo2_thresholds["warning_below"]

        hr_thresholds = thresholds["heart_rate"]
        hr = reading.hr
        hr_abnormal = hr is not None and (
            hr > hr_thresholds["warning_above"] or hr < hr_thresholds["warning_below"]
        )
        observed_abnormal["heart_rate"] = hr_abnormal
        if hr is not None:
            if hr > hr_thresholds["warning_above"]:
                severity = "critical" if hr > hr_thresholds["critical_above"] else "warning"
                threshold = (
                    hr_thresholds["critical_above"]
                    if severity == "critical"
                    else hr_thresholds["warning_above"]
                )
                direction = "high"
            elif hr < hr_thresholds["warning_below"]:
                severity = "critical" if hr < hr_thresholds["critical_below"] else "warning"
                threshold = (
                    hr_thresholds["critical_below"]
                    if severity == "critical"
                    else hr_thresholds["warning_below"]
                )
                direction = "low"
            else:
                direction = ""
                severity = "warning"
                threshold = 0
            if direction:
                findings.append(
                    RuleFinding(
                        type=f"heart_rate_{direction}",
                        metric="heart_rate",
                        observed=hr,
                        threshold=threshold,
                        severity=severity,
                        kind="threshold",
                        explanation=(
                            f"Heart rate {hr} is {direction} the illustrative "
                            f"{severity} threshold."
                        ),
                    )
                )

        bp_thresholds = thresholds["systolic_bp"]
        systolic_bp = reading.sys_bp
        bp_abnormal = systolic_bp is not None and (
            systolic_bp > bp_thresholds["warning_above"]
            or systolic_bp < bp_thresholds["warning_below"]
        )
        observed_abnormal["systolic_bp"] = bp_abnormal
        if systolic_bp is not None:
            if systolic_bp > bp_thresholds["warning_above"]:
                severity = (
                    "critical"
                    if systolic_bp > bp_thresholds["critical_above"]
                    else "warning"
                )
                threshold = (
                    bp_thresholds["critical_above"]
                    if severity == "critical"
                    else bp_thresholds["warning_above"]
                )
                direction = "high"
            elif systolic_bp < bp_thresholds["warning_below"]:
                severity = (
                    "critical"
                    if systolic_bp < bp_thresholds["critical_below"]
                    else "warning"
                )
                threshold = (
                    bp_thresholds["critical_below"]
                    if severity == "critical"
                    else bp_thresholds["warning_below"]
                )
                direction = "low"
            else:
                direction = ""
                severity = "warning"
                threshold = 0
            if direction:
                findings.append(
                    RuleFinding(
                        type=f"systolic_bp_{direction}",
                        metric="systolic_bp",
                        observed=systolic_bp,
                        threshold=threshold,
                        severity=severity,
                        kind="threshold",
                        explanation=(
                            f"Systolic BP {systolic_bp} is {direction} the "
                            f"illustrative {severity} threshold."
                        ),
                    )
                )

        window_size = settings.trend_window
        trend_readings = (history + [reading])[-window_size:]
        spo2_values = [item.spo2 for item in trend_readings]
        if (
            len(trend_readings) == window_size
            and all(item.quality == "ok" for item in trend_readings)
            and all(value is not None for value in spo2_values)
        ):
            valid_spo2 = [value for value in spo2_values if value is not None]
            if (
                all(left >= right for left, right in zip(valid_spo2, valid_spo2[1:]))
                and valid_spo2[0] - valid_spo2[-1] >= 3
            ):
                findings.append(
                    RuleFinding(
                        type="spo2_decline",
                        metric="spo2",
                        observed=valid_spo2[-1],
                        threshold=valid_spo2[0] - 3,
                        severity="warning",
                        kind="trend",
                        explanation=(
                            f"SpO2 declined from {valid_spo2[0]} to {valid_spo2[-1]} "
                            f"over {window_size} non-increasing readings."
                        ),
                    )
                )

    abnormal_counts: dict[str, int] = {}
    for metric, is_abnormal in observed_abnormal.items():
        count = 0
        for previous in reversed(history):
            value = _metric_value(previous, metric)
            if previous.quality != "ok" or value is None or not _is_abnormal(metric, value, thresholds):
                break
            count += 1
        if is_abnormal:
            count += 1
        abnormal_counts[metric] = count

    for finding_index, finding in enumerate(findings):
        if (
            finding.kind == "threshold"
            and abnormal_counts.get(
                "spo2" if finding.metric == "spo2" else finding.metric, 0
            )
            >= 3
            and finding.severity == "warning"
        ):
            findings[finding_index] = RuleFinding(
                type=finding.type,
                metric=finding.metric,
                observed=finding.observed,
                threshold=finding.threshold,
                severity="critical",
                kind=finding.kind,
                explanation=f"{finding.explanation} Three consecutive abnormal readings.",
            )

    return RuleEvaluation(findings=findings, consecutive_abnormal=abnormal_counts)


def is_normal_for_finding(
    finding_type: str,
    reading: Reading,
    *,
    now: datetime | None = None,
) -> bool:
    if finding_type == "signal_lost":
        current_time = now or datetime.now(timezone.utc)
        return (
            reading.quality == "ok"
            and current_time - reading.ts
            <= timedelta(seconds=settings.stale_seconds)
        )
    if reading.quality != "ok":
        return False
    thresholds = demo_thresholds()
    if finding_type == "spo2_low":
        return reading.spo2 is not None and reading.spo2 >= thresholds["spo2"]["warning_below"]
    if finding_type.startswith("heart_rate_"):
        return reading.hr is not None and not _is_abnormal("heart_rate", reading.hr, thresholds)
    if finding_type.startswith("systolic_bp_"):
        return reading.sys_bp is not None and not _is_abnormal(
            "systolic_bp", reading.sys_bp, thresholds
        )
    if finding_type == "spo2_decline":
        return True
    return False


def _metric_value(reading: Reading, metric: str) -> int | None:
    if metric == "spo2":
        return reading.spo2
    if metric == "heart_rate":
        return reading.hr
    if metric == "systolic_bp":
        return reading.sys_bp
    return None


def _is_abnormal(metric: str, value: int, thresholds: dict[str, dict[str, int]]) -> bool:
    metric_thresholds = thresholds[metric]
    return (
        value < metric_thresholds["warning_below"]
        or (
            "warning_above" in metric_thresholds
            and value > metric_thresholds["warning_above"]
        )
    )
