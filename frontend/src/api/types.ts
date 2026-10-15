export type ReadingQuality = "ok" | "missing" | "stale";
export type RiskBand = "High" | "Medium" | "Routine";
export type AlertSeverity = "warning" | "critical";
export type AlertKind = "threshold" | "trend" | "signal" | "advisory";
export type AlertStatus = "active" | "acknowledged" | "escalated" | "resolved";
export type DashboardFilter = "all" | "needs_review" | "acknowledged";

export interface Reading {
  patient_id: string;
  ts: string;
  hr: number | null;
  sys_bp: number | null;
  dia_bp: number | null;
  spo2: number | null;
  quality: ReadingQuality;
}

export interface Patient {
  id: string;
  name: string;
  age: number;
  scenario: string | null;
}

export interface Alert {
  id: string;
  patient_id: string;
  type: string;
  metric: string;
  observed: number | string | null;
  threshold: number | string | null;
  ai_explanation: string | null;
  severity: AlertSeverity;
  kind: AlertKind;
  explanation: string;
  evidence: Reading[];
  status: AlertStatus;
  created_at: string;
  updated_at: string;
  acknowledged_at: string | null;
  ack_note: string | null;
  occurrences: number;
}

export interface ScoreBreakdownItem {
  factor: string;
  points: number;
  reason: string;
}

export interface PatientStatus {
  patient: Patient;
  latest: Reading | null;
  risk_band: RiskBand;
  score: number;
  score_breakdown: ScoreBreakdownItem[];
  active_alert_count: number;
  data_freshness_seconds: number;
  simulated: true;
}

export interface HealthResponse {
  status: string;
  version: string;
  simulated: true;
  message: string;
}

export interface DashboardResponse {
  patients: PatientStatus[];
  simulated: true;
}

export interface PatientProfileResponse {
  patient: Patient;
  latest: Reading;
  active_alerts: Alert[];
  simulated: true;
}

export interface PatientHistoryResponse {
  patient_id: string;
  readings: Reading[];
  alerts: Alert[];
  simulated: true;
}

export interface SimulationTickResponse {
  tick: number;
  readings: Reading[];
  simulated: true;
}

export interface AlertListResponse {
  alerts: Alert[];
  simulated: true;
}

export interface AcknowledgeRequest {
  note?: string;
}

export interface AlertResponse {
  alert: Alert;
  simulated: true;
}

export interface ThresholdsResponse {
  demo_only: true;
  label: string;
  thresholds: Record<string, Record<string, number>>;
}

export interface ScenarioListResponse {
  scenarios: string[];
  simulated: true;
}

export interface ScenarioResponse {
  scenario: string;
  patient_id: string;
  duration_ticks: number;
  tick: number;
  latest: Reading;
  simulated: true;
}

export interface AuditEntry {
  ts: string;
  event: string;
  details: Record<string, unknown>;
  simulated: true;
}

export interface AuditResponse {
  events: AuditEntry[];
  simulated: true;
}

export interface HandoffResponse {
  generated_at: string;
  simulated: true;
  new_alerts: Alert[];
  worsening: Alert[];
  resolved: Alert[];
  unacknowledged: Alert[];
  text: string;
  ai_text: string | null;
  ai_used: boolean;
}

export interface ApiErrorBody {
  error: string;
  detail: string;
}

export interface StreamEvent {
  type: "tick" | "alert" | "ranking" | string;
  data: Record<string, unknown>;
}
