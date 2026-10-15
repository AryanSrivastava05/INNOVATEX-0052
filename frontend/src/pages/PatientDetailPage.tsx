import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  acknowledgeAlert,
  ApiError,
  getAudit,
  getDashboard,
  getPatient,
  getPatientHistory,
  getThresholds,
  postSimulationTick,
} from "../api/client";
import type {
  Alert,
  AuditEntry,
  PatientHistoryResponse,
  PatientProfileResponse,
  PatientStatus,
  Reading,
  ThresholdsResponse,
} from "../api/types";
import { AppShell } from "../components/shell";
import { useLiveUpdates } from "../components/LiveUpdates";
import { Card, InitialsAvatar, PriorityBadge, StatusPill, VitalCard } from "../components/ui";

type Metric = "hr" | "sys_bp" | "dia_bp" | "spo2";
type RangeHours = 6 | 12 | 24;
type DetailData = {
  profile: PatientProfileResponse;
  history: PatientHistoryResponse;
  thresholds: ThresholdsResponse;
  audit: AuditEntry[];
  status?: PatientStatus;
};

const metricOptions: Array<{ key: Metric; label: string; unit: string }> = [
  { key: "hr", label: "Heart rate", unit: "bpm" },
  { key: "sys_bp", label: "Systolic BP", unit: "mmHg" },
  { key: "dia_bp", label: "Diastolic BP", unit: "mmHg" },
  { key: "spo2", label: "SpO₂", unit: "%" },
];

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? `${error.error}: ${error.detail}` : error instanceof Error ? error.message : "An unexpected error occurred.";
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function activeSignalLost(alerts: Alert[]): boolean {
  return alerts.some((alert) => alert.type === "signal_lost" && (alert.status === "active" || alert.status === "escalated"));
}

function matchesThreshold(value: number | null, limits: Record<string, number> | undefined): "normal" | "warning" | "critical" | "missing" {
  if (value == null) return "missing";
  if (!limits) return "normal";
  if ((limits.critical_below !== undefined && value < limits.critical_below) || (limits.critical_above !== undefined && value > limits.critical_above)) return "critical";
  if ((limits.warning_below !== undefined && value < limits.warning_below) || (limits.warning_above !== undefined && value > limits.warning_above)) return "warning";
  return "normal";
}

function thresholdLabel(limits: Record<string, number> | undefined, unit: string): string {
  if (!limits) return "Threshold unavailable";
  const lower = limits.warning_below !== undefined ? `< ${limits.warning_below}` : null;
  const upper = limits.warning_above !== undefined ? `> ${limits.warning_above}` : null;
  if (lower && upper) return `Demo threshold: ${lower} or ${upper} ${unit}`;
  if (lower) return `Demo threshold: ${lower} ${unit}`;
  if (upper) return `Demo threshold: ${upper} ${unit}`;
  return "Illustrative demo threshold";
}

function getReadingTimeAgo(reading: Reading): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(reading.ts).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function chartThresholds(metric: Metric, thresholds: ThresholdsResponse): Array<{ value: number; level: "warning" | "critical"; direction: "below" | "above" }> {
  if (metric === "dia_bp") return [];
  const group = metric === "hr" ? thresholds.thresholds.heart_rate
    : metric === "spo2" ? thresholds.thresholds.spo2
      : thresholds.thresholds.systolic_bp;
  if (!group) return [];
  return ([
    ["warning_below", "warning", "below"],
    ["warning_above", "warning", "above"],
    ["critical_below", "critical", "below"],
    ["critical_above", "critical", "above"],
  ] as const).flatMap(([key, level, direction]) => {
    const value = group[key];
    return value === undefined ? [] : [{ value, level, direction }];
  });
}

function readingMetric(reading: Reading, metric: Metric): number | null {
  return reading.quality === "ok" ? reading[metric] : null;
}

function isAlertReading(alerts: Alert[], reading: Reading): boolean {
  return alerts.some((alert) => alert.evidence.some((evidence) => evidence.ts === reading.ts));
}

function ChartSection({ data }: { data: DetailData }) {
  const [metric, setMetric] = useState<Metric>("sys_bp");
  const [range, setRange] = useState<RangeHours>(24);
  const selected = metricOptions.find((option) => option.key === metric)!;
  const chartData = useMemo(() => {
    const after = Date.now() - range * 60 * 60 * 1000;
    return data.history.readings
      .filter((reading) => new Date(reading.ts).getTime() >= after)
      .map((reading) => ({
        ts: reading.ts,
        time: new Date(reading.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        value: readingMetric(reading, metric),
        alert: isAlertReading(data.history.alerts, reading),
        quality: reading.quality,
      }));
  }, [data.history, metric, range]);
  const thresholds = chartThresholds(metric, data.thresholds);
  return (
    <Card className="space-y-4">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h2 className="text-base font-semibold">Biometric trend history</h2>
          <p className="mt-1 text-xs text-slate-500">Readings are shown as recorded; missing and stale samples break the trend line.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="sr-only" htmlFor="metric">Trend metric</label>
          <select id="metric" className="h-9 rounded border border-slate-300 bg-white px-2 text-sm" value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>
            {metricOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
          </select>
          <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-0.5" aria-label="Trend range">
            {([6, 12, 24] as const).map((hours) => (
              <button key={hours} type="button" onClick={() => setRange(hours)} className={`rounded-full px-3 py-1 text-xs font-semibold ${range === hours ? "bg-white text-primary" : "text-slate-600"}`}>{hours}h</button>
            ))}
          </div>
        </div>
      </div>
      {chartData.length === 0 ? (
        <div className="flex h-60 items-center justify-center rounded-lg bg-surface-container-low text-sm text-slate-600">No readings in the selected {range}h window.</div>
      ) : chartData.every((point) => point.value === null) ? (
        <div className="flex h-60 items-center justify-center rounded-lg bg-surface-container-low text-sm text-slate-600">No usable {selected.label.toLowerCase()} readings in the selected window.</div>
      ) : (
        <div className="h-64 w-full rounded-lg bg-surface-container-low p-2 sm:h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 12, right: 18, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="#dae2fd" strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 11, fill: "#707881" }} minTickGap={28} />
              <YAxis width={42} tick={{ fontSize: 11, fill: "#707881" }} domain={["auto", "auto"]} />
              <Tooltip
                labelFormatter={(_, payload) => {
                  const timestamp = payload[0]?.payload?.ts;
                  return typeof timestamp === "string" ? formatTimestamp(timestamp) : "";
                }}
                formatter={(value, _name, item) => [
                  typeof value === "number" ? `${value} ${selected.unit}` : `No reading (${item.payload.quality})`,
                  selected.label,
                ]}
              />
              {thresholds.map((threshold) => (
                <ReferenceLine
                  key={`${threshold.level}-${threshold.direction}-${threshold.value}`}
                  y={threshold.value}
                  stroke={threshold.level === "critical" ? "#ba1a1a" : "#d97706"}
                  strokeDasharray="6 4"
                  label={{ value: `${threshold.level} ${threshold.direction} ${threshold.value}`, fill: threshold.level === "critical" ? "#ba1a1a" : "#92400e", fontSize: 10 }}
                />
              ))}
              <Line type="monotone" dataKey="value" stroke="#006194" strokeWidth={2.5} connectNulls={false} isAnimationActive={false} dot={(props) => {
                const point = props.payload as { alert?: boolean };
                return <circle key={`${props.cx}-${props.cy}`} cx={props.cx} cy={props.cy} r={point.alert ? 5 : 3} fill={point.alert ? "#ba1a1a" : "#ffffff"} stroke={point.alert ? "#ba1a1a" : "#006194"} strokeWidth={2} />;
              }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="text-xs text-slate-500">Dashed line: illustrative threshold from demo configuration. Red markers: readings cited as alert evidence.</p>
    </Card>
  );
}

function PrioritizationCard({ status, alerts }: { status?: PatientStatus; alerts: Alert[] }) {
  const escalated = alerts.some((alert) => alert.status === "escalated");
  const explanation = alerts[0]?.explanation;
  return (
    <Card className="bg-surface-container p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Why this patient is prioritized</h2>
        <div className="flex gap-2">
          {status && <PriorityBadge band={status.risk_band} score={status.score} />}
          {escalated && <StatusPill status="escalated" />}
        </div>
      </div>
      {explanation ? <p className="mt-3 text-sm leading-relaxed text-slate-700">{explanation}</p> : (
        <p className="mt-3 text-sm text-slate-600">No active alert explanation is available for this patient.</p>
      )}
      {alerts.length > 0 && (
        <div className="mt-4 space-y-3">
          {alerts.map((alert) => (
            <div key={alert.id} className="rounded-lg border border-white/80 bg-white/70 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold">{alert.metric.replace(/_/g, " ")} · {String(alert.observed ?? "No reading")}</p>
                <div className="flex items-center gap-2">
                  <StatusPill status={alert.severity === "critical" ? "Critical" : "Warning"} />
                  {alert.status === "escalated" && <StatusPill status="escalated" />}
                </div>
              </div>
              <p className="mt-1 text-xs text-slate-600">{alert.explanation}</p>
              {alert.evidence.length > 0 && (
                <div className="mt-2 border-t border-slate-100 pt-2">
                  <p className="text-xs font-semibold text-slate-600">Evidence readings</p>
                  <ul className="mt-1 flex flex-wrap gap-2">
                    {alert.evidence.map((reading) => (
                      <li key={`${alert.id}-${reading.ts}`} className="rounded-full border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700">
                        {reading.hr == null ? "" : `HR ${reading.hr} · `}
                        {reading.sys_bp == null ? "" : `BP ${reading.sys_bp}/${reading.dia_bp ?? "—"} · `}
                        {reading.spo2 == null ? "" : `SpO₂ ${reading.spo2}% · `}
                        {formatTimestamp(reading.ts)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="mt-4 border-t border-white/80 pt-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Score breakdown</h3>
        {status && status.score_breakdown.length > 0 ? (
          <ul className="mt-2 divide-y divide-white/80">
            {status.score_breakdown.map((item, index) => (
              <li key={`${item.factor}-${index}`} className="flex items-start justify-between gap-4 py-2 text-sm">
                <span className="text-slate-700">{item.reason}</span>
                <span className="shrink-0 font-semibold tabular-nums text-primary">{item.points > 0 ? "+" : ""}{item.points}</span>
              </li>
            ))}
          </ul>
        ) : <p className="mt-2 text-sm text-slate-600">No priority score breakdown is available.</p>}
      </div>
    </Card>
  );
}

function AuditTrail({ events, patientId }: { events: AuditEntry[]; patientId: string }) {
  const relevant = events.filter((event) => event.details.patient_id === patientId || JSON.stringify(event.details).includes(patientId));
  if (relevant.length === 0) return <p className="py-3 text-sm text-slate-600">No audit events recorded for this patient.</p>;
  return (
    <ol className="mt-3 space-y-3">
      {relevant.map((event, index) => (
        <li key={`${event.ts}-${event.event}-${index}`} className="flex gap-3 border-l-2 border-primary-fixed pl-3">
          <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
          <div className="min-w-0">
            <p className="text-sm font-semibold capitalize">{event.event.replace(/_/g, " ")}</p>
            <p className="mt-0.5 break-words text-xs text-slate-600">{formatTimestamp(event.ts)} · {JSON.stringify(event.details)}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ProviderActions({ data, onRefresh }: { data: DetailData; onRefresh: () => void }) {
  const [note, setNote] = useState(() => localStorage.getItem(`pulsecare-note-${data.profile.patient.id}`) ?? "");
  const [acknowledgeNote, setAcknowledgeNote] = useState("");
  const [message, setMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const alert = data.profile.active_alerts.find((item) => item.status === "active" || item.status === "escalated");

  async function acknowledge() {
    if (!alert) return;
    setBusy(true);
    setActionError("");
    try {
      await acknowledgeAlert(alert.id, { note: acknowledgeNote.trim() || undefined });
      setMessage("Alert acknowledged.");
      onRefresh();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  function saveNote() {
    try {
      localStorage.setItem(`pulsecare-note-${data.profile.patient.id}`, note);
      setMessage("Note saved in this browser.");
      setActionError("");
    } catch (error) {
      setActionError(errorMessage(error));
    }
  }

  async function retest() {
    setBusy(true);
    setActionError("");
    try {
      await postSimulationTick();
      setMessage("Simulation advanced. Telemetry refreshed.");
      onRefresh();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Provider actions</h2>
        <p className="mt-1 text-xs text-slate-500">Actions operate on the synthetic demo only.</p>
      </div>
      <div className="space-y-2">
        <label className="block text-xs font-semibold text-slate-700" htmlFor="ack-note">Acknowledgement note (optional)</label>
        <textarea id="ack-note" rows={2} value={acknowledgeNote} onChange={(event) => setAcknowledgeNote(event.target.value)} className="w-full rounded border border-slate-300 bg-white p-2.5 text-sm" placeholder="Add context to the alert acknowledgement" />
        <button type="button" onClick={acknowledge} disabled={!alert || busy} className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-container disabled:cursor-not-allowed disabled:opacity-50">
          <span className="material-symbols-outlined text-base" aria-hidden="true">task_alt</span>
          {busy ? "Working…" : alert ? "Acknowledge alert" : "No active alert to acknowledge"}
        </button>
      </div>
      <div className="space-y-2 border-t border-slate-100 pt-3">
        <label className="block text-xs font-semibold text-slate-700" htmlFor="provider-note">Provider note</label>
        <textarea id="provider-note" rows={3} value={note} onChange={(event) => setNote(event.target.value)} className="w-full rounded border border-slate-300 bg-white p-2.5 text-sm" placeholder="Record a local review note…" />
        <button type="button" onClick={saveNote} className="rounded border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">Save note locally</button>
        <p className="text-xs text-slate-500">Notes stay in this browser and are not sent to the backend.</p>
      </div>
      <button type="button" onClick={retest} disabled={busy} className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
        <span className="material-symbols-outlined text-base text-secondary" aria-hidden="true">replay</span>
        Simulate re-test
      </button>
      {message && <p className="text-sm font-medium text-tertiary" role="status">{message}</p>}
      {actionError && <p className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800" role="alert">{actionError}</p>}
    </Card>
  );
}

export default function PatientDetailPage() {
  const { id = "" } = useParams();
  const [data, setData] = useState<DetailData>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const { revision } = useLiveUpdates();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all([
      getPatient(id),
      getPatientHistory(id, 100),
      getThresholds(),
      getAudit(50),
      getDashboard("all"),
    ]).then(([profile, history, thresholds, audit, dashboard]) => {
      if (cancelled) return;
      setData({
        profile,
        history,
        thresholds,
        audit: audit.events,
        status: dashboard.patients.find((patient) => patient.patient.id === id),
      });
    }).catch((reason: unknown) => {
      if (!cancelled) setError(errorMessage(reason));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [id, refreshKey, revision]);

  if (loading) return <AppShell><div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-600" role="status">Loading patient telemetry…</div></AppShell>;
  if (error) return <AppShell><div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-900" role="alert"><h1 className="font-semibold">Unable to load patient</h1><p className="mt-1">{error}</p></div></AppShell>;
  if (!data) return <AppShell><div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-600">No patient data is available.</div></AppShell>;

  const { profile, thresholds } = data;
  const patient = profile.patient;
  const latest = profile.latest;
  const signalLost = latest.quality !== "ok" || activeSignalLost(profile.active_alerts);
  const hrStatus = latest.hr == null ? "missing" : signalLost ? "stale" : matchesThreshold(latest.hr, thresholds.thresholds.heart_rate);
  const bpStatus = latest.sys_bp == null ? "missing" : signalLost ? "stale" : matchesThreshold(latest.sys_bp, thresholds.thresholds.systolic_bp);
  const spo2Status = latest.spo2 == null ? "missing" : signalLost ? "stale" : matchesThreshold(latest.spo2, thresholds.thresholds.spo2);
  const alerts = data.history.alerts.filter((alert) => alert.status === "active" || alert.status === "escalated");

  return (
    <AppShell>
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2">
        <div className="space-y-4 md:col-span-2">
          <Card className="relative overflow-hidden border-l-4 border-l-error">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <InitialsAvatar name={patient.name} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="truncate text-xl font-semibold">{patient.name}</h1>
                    <span className="rounded bg-surface-container-high px-2 py-0.5 text-xs font-semibold text-slate-700">Age {patient.age}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">ID: {patient.id}{patient.scenario ? ` · ${patient.scenario}` : ""}</p>
                </div>
              </div>
              {data.status && <PriorityBadge band={data.status.risk_band} score={data.status.score} />}
            </div>
            {alerts.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
                <span className="flex items-center gap-2 font-semibold"><span className="material-symbols-outlined text-base" aria-hidden="true">warning</span>{alerts[0].explanation}</span>
                <span className="text-xs">{formatTimestamp(alerts[0].created_at)}</span>
              </div>
            )}
            <div className={`mt-4 flex flex-wrap items-center justify-between gap-2 text-xs ${signalLost ? "text-amber-800" : "text-slate-500"}`}>
              <span className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${signalLost ? "bg-amber-500" : "bg-emerald-600"}`} />{signalLost ? "Signal needs review" : `${getReadingTimeAgo(latest)} · Fresh reading`}</span>
              <span>Latest reading: {formatTimestamp(latest.ts)}</span>
            </div>
          </Card>
        </div>
        <section className="space-y-3 md:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-base font-semibold"><span className="material-symbols-outlined text-primary" aria-hidden="true">monitor_heart</span>Real-time telemetry</h2>
            <span className="rounded-full bg-secondary-fixed px-3 py-1 text-xs font-medium text-on-secondary-fixed">Auto-refresh 5s</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <VitalCard
              label="Blood pressure"
              value={latest.sys_bp == null ? null : `${latest.sys_bp}/${latest.dia_bp ?? "—"}`}
              unit="mmHg"
              threshold={thresholdLabel(thresholds.thresholds.systolic_bp, "mmHg")}
              status={bpStatus}
              icon="blood_pressure"
            />
            <VitalCard
              label="Pulse"
              value={latest.hr}
              unit="bpm"
              threshold={thresholdLabel(thresholds.thresholds.heart_rate, "bpm")}
              status={hrStatus}
              icon="favorite"
            />
            <VitalCard
              label="SpO₂ saturation"
              value={latest.spo2}
              unit="%"
              threshold={thresholdLabel(thresholds.thresholds.spo2, "%")}
              status={spo2Status}
              icon="air"
            />
          </div>
          {thresholds.label && <p className="text-xs text-slate-500">{thresholds.label}</p>}
        </section>
        <PrioritizationCard status={data.status} alerts={alerts} />
        <ChartSection data={data} />
        <Card>
          <h2 className="flex items-center gap-2 text-base font-semibold"><span className="material-symbols-outlined text-slate-500" aria-hidden="true">schedule</span>Telemetry audit trail</h2>
          <AuditTrail events={data.audit} patientId={patient.id} />
        </Card>
        <ProviderActions data={data} onRefresh={() => setRefreshKey((key) => key + 1)} />
      </div>
    </AppShell>
  );
}
