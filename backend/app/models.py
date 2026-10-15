from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Reading(BaseModel):
    patient_id: str
    ts: datetime
    hr: int | None = None
    sys_bp: int | None = None
    dia_bp: int | None = None
    spo2: int | None = None
    quality: Literal["ok", "missing", "stale"]


class Patient(BaseModel):
    id: str
    name: str
    age: int
    scenario: str | None = None


class Alert(BaseModel):
    id: str
    patient_id: str
    type: str
    metric: str
    observed: int | float | str | None
    threshold: int | float | str | None
    ai_explanation: str | None = None
    severity: Literal["warning", "critical"]
    kind: Literal["threshold", "trend", "signal", "advisory"]
    explanation: str
    evidence: list[Reading]
    status: Literal["active", "acknowledged", "escalated", "resolved"]
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None = None
    ack_note: str | None = None
    occurrences: int


class ScoreBreakdownItem(BaseModel):
    factor: str
    points: int
    reason: str


class PatientStatus(BaseModel):
    patient: Patient
    latest: Reading | None
    risk_band: Literal["High", "Medium", "Routine"]
    score: int
    score_breakdown: list[ScoreBreakdownItem]
    active_alert_count: int
    data_freshness_seconds: float
    simulated: Literal[True] = True


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
    simulated: Literal[True]
    message: str


class DashboardResponse(BaseModel):
    patients: list[PatientStatus]
    simulated: Literal[True] = True


class PatientProfileResponse(BaseModel):
    patient: Patient
    latest: Reading
    active_alerts: list[Alert]
    simulated: Literal[True] = True


class PatientHistoryResponse(BaseModel):
    patient_id: str
    readings: list[Reading]
    alerts: list[Alert]
    simulated: Literal[True] = True


class SimulationTickResponse(BaseModel):
    tick: int
    readings: list[Reading]
    simulated: Literal[True] = True


class AlertListResponse(BaseModel):
    alerts: list[Alert]
    simulated: Literal[True] = True


class AcknowledgeRequest(BaseModel):
    note: str | None = None


class AlertResponse(BaseModel):
    alert: Alert
    simulated: Literal[True] = True


class ThresholdsResponse(BaseModel):
    demo_only: Literal[True] = True
    label: str
    thresholds: dict[str, dict[str, int]]


class ScenarioListResponse(BaseModel):
    scenarios: list[str]
    simulated: Literal[True] = True


class ScenarioResponse(BaseModel):
    scenario: str
    patient_id: str
    duration_ticks: int
    tick: int
    latest: Reading
    simulated: Literal[True] = True


class AuditEntry(BaseModel):
    ts: datetime
    event: str
    details: dict[str, object]
    simulated: Literal[True] = True


class AuditResponse(BaseModel):
    events: list[AuditEntry]
    simulated: Literal[True] = True


class HandoffResponse(BaseModel):
    generated_at: datetime
    simulated: Literal[True] = True
    new_alerts: list[Alert]
    worsening: list[Alert]
    resolved: list[Alert]
    unacknowledged: list[Alert]
    text: str
    ai_text: str | None = None
    ai_used: bool = False
