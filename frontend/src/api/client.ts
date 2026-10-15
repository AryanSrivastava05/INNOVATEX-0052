import type {
  AcknowledgeRequest,
  AlertListResponse,
  AlertResponse,
  AuditResponse,
  DashboardFilter,
  DashboardResponse,
  HealthResponse,
  HandoffResponse,
  PatientHistoryResponse,
  PatientProfileResponse,
  ScenarioListResponse,
  ScenarioResponse,
  SimulationTickResponse,
  StreamEvent,
  ThresholdsResponse,
} from "./types";

const apiBaseUrl = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const apiRoot = `${apiBaseUrl}/api`;
const demoToken = import.meta.env.VITE_DEMO_TOKEN;

export class ApiError extends Error {
  readonly status: number;
  readonly error: string;
  readonly detail: string;

  constructor(status: number, error: string, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.error = error;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  admin = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (admin && demoToken) headers.set("X-Demo-Token", demoToken);

  const response = await fetch(`${apiRoot}${path}`, { ...options, headers });
  if (!response.ok) {
    let body: Partial<{ error: string; detail: string }> = {};
    try {
      body = (await response.json()) as typeof body;
    } catch {
      throw new ApiError(response.status, "request_error", `Request failed (${response.status})`);
    }
    throw new ApiError(
      response.status,
      body.error || "request_error",
      body.detail || `Request failed (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request("/health");
}

export function getDashboard(
  filter: DashboardFilter = "all",
  q = "",
): Promise<DashboardResponse> {
  const params = new URLSearchParams({ filter, q });
  return request(`/dashboard?${params.toString()}`);
}

export function getPatient(patientId: string): Promise<PatientProfileResponse> {
  return request(`/patients/${encodeURIComponent(patientId)}`);
}

export function getPatientHistory(
  patientId: string,
  limit = 100,
): Promise<PatientHistoryResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return request(`/patients/${encodeURIComponent(patientId)}/history?${params.toString()}`);
}

export function getAlerts(status = "active"): Promise<AlertListResponse> {
  const params = new URLSearchParams({ status });
  return request(`/alerts?${params.toString()}`);
}

export function getAlert(alertId: string, ai = false): Promise<AlertResponse> {
  const params = new URLSearchParams({ ai: String(ai) });
  return request(`/alerts/${encodeURIComponent(alertId)}?${params.toString()}`);
}

export function acknowledgeAlert(
  alertId: string,
  body: AcknowledgeRequest = {},
): Promise<AlertResponse> {
  return request(
    `/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function postSimulationTick(): Promise<SimulationTickResponse> {
  return request("/simulation/tick", { method: "POST" }, true);
}

export function postScenario(
  name: string,
  patientId: string,
): Promise<ScenarioResponse> {
  const params = new URLSearchParams({ patient_id: patientId });
  return request(
    `/scenarios/${encodeURIComponent(name)}?${params.toString()}`,
    { method: "POST" },
    true,
  );
}

export function getScenarios(): Promise<ScenarioListResponse> {
  return request("/scenarios");
}

export function getThresholds(): Promise<ThresholdsResponse> {
  return request("/config/thresholds");
}

export function getHandoff(windowMinutes = 60): Promise<HandoffResponse> {
  const params = new URLSearchParams({ window_minutes: String(windowMinutes) });
  return request(`/handoff?${params.toString()}`);
}

export function getAudit(limit = 50): Promise<AuditResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return request(`/audit?${params.toString()}`);
}

export function connectToEventStream(
  onEvent: (event: StreamEvent) => void,
  onError: () => void,
  onOpen?: () => void,
): () => void {
  const source = new EventSource(`${apiRoot}/stream`);
  const eventTypes = ["tick", "alert", "ranking"] as const;
  for (const type of eventTypes) {
    source.addEventListener(type, (event: MessageEvent<string>) => {
      onEvent({ type, data: JSON.parse(event.data) as Record<string, unknown> });
    });
  }
  source.onerror = onError;
  source.onopen = () => onOpen?.();
  return () => source.close();
}
