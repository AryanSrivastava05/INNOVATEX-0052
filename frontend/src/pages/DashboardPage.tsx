import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getAlerts, getDashboard, getHandoff } from "../api/client";
import type { Alert, DashboardFilter, HandoffResponse, PatientStatus } from "../api/types";
import { AppShell } from "../components/shell";
import { useLiveUpdates } from "../components/LiveUpdates";
import { Card, InitialsAvatar, PriorityBadge, StatusPill } from "../components/ui";

type DashboardData = {
  patients: PatientStatus[];
  handoff: HandoffResponse;
  alerts: Alert[];
};

const filters: Array<{ value: DashboardFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "needs_review", label: "Needs review" },
  { value: "acknowledged", label: "Acknowledged" },
];

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? `${error.error}: ${error.detail}` : error instanceof Error ? error.message : "An unexpected error occurred.";
}

function timeAgo(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  return `${seconds}s ago`;
}

function signalLost(alerts: Alert[], patientId: string): boolean {
  return alerts.some((alert) => alert.patient_id === patientId && alert.type === "signal_lost" && (alert.status === "active" || alert.status === "escalated"));
}

function HandoffPanel({ handoff, patients }: { handoff: HandoffResponse; patients: PatientStatus[] }) {
  const names = new Map(patients.map((status) => [status.patient.id, status.patient.name]));
  const groups: Array<{ label: string; items: Alert[] }> = [
    { label: "New alerts", items: handoff.new_alerts },
    { label: "Worsening", items: handoff.worsening },
    { label: "Review needed", items: handoff.unacknowledged },
    { label: "Resolved", items: handoff.resolved },
  ];
  return (
    <Card className="lg:sticky lg:top-5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">Shift handoff</h2>
          <p className="mt-1 text-xs text-slate-500">Updated {new Date(handoff.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
        </div>
        <span className="material-symbols-outlined text-primary" aria-hidden="true">handover</span>
      </div>
      <p className="mt-3 whitespace-pre-line rounded-lg bg-surface-container-low p-3 text-sm leading-relaxed text-slate-700">{handoff.ai_text || handoff.text}</p>
      <div className="mt-4 space-y-4">
        {groups.map((group) => (
          <section key={group.label}>
            <h3 className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-600">
              {group.label}<span className="rounded-full bg-slate-100 px-2 py-0.5 tabular-nums">{group.items.length}</span>
            </h3>
            {group.items.length ? (
              <ul className="mt-2 space-y-2">
                {group.items.slice(0, 4).map((alert) => (
                  <li key={alert.id} className="rounded border border-slate-100 p-2">
                    <Link to={`/patients/${encodeURIComponent(alert.patient_id)}`} className="text-sm font-semibold text-primary hover:underline">
                      {names.get(alert.patient_id) || alert.patient_id} · {alert.patient_id}
                    </Link>
                    <p className="mt-0.5 line-clamp-2 text-xs text-slate-600">{alert.explanation}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="mt-2 text-xs text-slate-500">No items in this category.</p>}
          </section>
        ))}
      </div>
    </Card>
  );
}

function PatientQueueRow({ status, alerts }: { status: PatientStatus; alerts: Alert[] }) {
  const { patient, latest } = status;
  const isNoSignal = !latest || latest.quality === "missing" || signalLost(alerts, patient.id);
  const isStale = !isNoSignal && latest.quality === "stale";
  const accent = status.risk_band === "High" ? "border-l-error" : status.risk_band === "Medium" ? "border-l-amber-500" : "border-l-slate-300";
  return (
    <Link to={`/patients/${encodeURIComponent(patient.id)}`} className={`block border-b border-slate-100 border-l-4 ${accent} px-4 py-4 transition-colors hover:bg-slate-50 focus:bg-slate-50`}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          <InitialsAvatar name={patient.name} className="h-10 w-10" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-on-surface">{patient.name}</p>
            <p className="mt-0.5 text-xs text-slate-500">{patient.id} · Age {patient.age}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PriorityBadge band={status.risk_band} score={status.score} />
          {isNoSignal && <StatusPill status="No signal" />}
          {!isNoSignal && isStale && <StatusPill status="Stale" />}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
        <div><span className="block text-slate-500">HR</span><span className={`mt-0.5 block font-semibold tabular-nums ${latest?.hr == null || isNoSignal ? "text-slate-400" : isStale ? "text-amber-700" : "text-on-surface"}`}>{latest?.hr == null || isNoSignal ? "—" : `${latest.hr} bpm`}</span></div>
        <div><span className="block text-slate-500">BP</span><span className={`mt-0.5 block font-semibold tabular-nums ${latest?.sys_bp == null || isNoSignal ? "text-slate-400" : isStale ? "text-amber-700" : "text-on-surface"}`}>{latest?.sys_bp == null || isNoSignal ? "—" : `${latest.sys_bp}/${latest.dia_bp ?? "—"}`}</span></div>
        <div><span className="block text-slate-500">SpO₂</span><span className={`mt-0.5 block font-semibold tabular-nums ${latest?.spo2 == null || isNoSignal ? "text-slate-400" : isStale ? "text-amber-700" : "text-on-surface"}`}>{latest?.spo2 == null || isNoSignal ? "—" : `${latest.spo2}%`}</span></div>
        <div><span className="block text-slate-500">Priority score</span><span className="mt-0.5 block font-semibold tabular-nums">{status.score}</span></div>
        <div><span className="block text-slate-500">Active alerts</span><span className="mt-0.5 block font-semibold tabular-nums">{status.active_alert_count}</span></div>
        <div><span className={`block ${isStale || isNoSignal ? "text-amber-700" : "text-slate-500"}`}>Latest reading</span><span className={`mt-0.5 block font-semibold tabular-nums ${isStale || isNoSignal ? "text-amber-700" : "text-on-surface"}`}>{latest ? timeAgo(latest.ts) : "—"}</span></div>
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const [filter, setFilter] = useState<DashboardFilter>("all");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [data, setData] = useState<DashboardData>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const { revision } = useLiveUpdates();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all([
      getDashboard(filter, debouncedQuery),
      getHandoff(),
      getAlerts("active"),
      getAlerts("escalated"),
    ]).then(([dashboard, handoff, active, escalated]) => {
      if (cancelled) return;
      setData({
        patients: dashboard.patients,
        handoff,
        alerts: [...active.alerts, ...escalated.alerts],
      });
    }).catch((reason: unknown) => {
      if (!cancelled) setError(errorMessage(reason));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [filter, debouncedQuery, refreshKey, revision]);

  const counts = useMemo(() => {
    const patients = data?.patients ?? [];
    return {
      High: patients.filter((patient) => patient.risk_band === "High").length,
      Medium: patients.filter((patient) => patient.risk_band === "Medium").length,
      Routine: patients.filter((patient) => patient.risk_band === "Routine").length,
    };
  }, [data]);

  return (
    <AppShell>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {([
          ["High", "text-red-800", "bg-red-50"],
          ["Medium", "text-amber-800", "bg-amber-50"],
          ["Routine", "text-slate-700", "bg-white"],
        ] as const).map(([band, color, background]) => (
          <Card key={band} className={`${background} p-3`}>
            <p className={`text-xs font-semibold uppercase tracking-wide ${color}`}>{band}</p>
            <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{counts[band]}</p>
            <p className="text-xs text-slate-500">patients</p>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="min-w-0">
          <Card className="overflow-hidden p-0">
            <div className="space-y-4 border-b border-slate-200 p-4">
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                <div>
                  <h1 className="text-lg font-semibold">Priority queue</h1>
                  <p className="mt-1 text-xs text-slate-500">Ranked for review by transparent demo score, not a clinical probability.</p>
                </div>
                <label className="relative block sm:w-64">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-base text-slate-400" aria-hidden="true">search</span>
                  <input aria-label="Search patients" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name or patient ID" className="h-10 w-full rounded border border-slate-300 bg-white pl-9 pr-3 text-sm" />
                </label>
              </div>
              <div className="flex gap-1 overflow-x-auto border-b border-slate-100" role="tablist" aria-label="Filter patients">
                {filters.map((item) => (
                  <button key={item.value} type="button" role="tab" aria-selected={filter === item.value} onClick={() => setFilter(item.value)} className={`shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${filter === item.value ? "border-primary text-primary" : "border-transparent text-slate-600 hover:text-slate-900"}`}>{item.label}</button>
                ))}
              </div>
            </div>
            {loading ? <div className="p-8 text-center text-sm text-slate-600" role="status">Loading patient queue…</div>
              : error ? <div className="m-4 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-900" role="alert"><p className="font-semibold">Unable to load overview</p><p className="mt-1">{error}</p><button type="button" onClick={() => setRefreshKey((key) => key + 1)} className="mt-3 rounded border border-red-300 bg-white px-3 py-1.5 font-semibold">Retry</button></div>
                : !data || data.patients.length === 0 ? <div className="p-8 text-center"><p className="font-semibold text-slate-700">No patients found</p><p className="mt-1 text-sm text-slate-500">{debouncedQuery ? "Try another name or ID." : `No patients match the ${filters.find((item) => item.value === filter)?.label.toLowerCase()} filter.`}</p></div>
                  : <div>{data.patients.map((status) => <PatientQueueRow key={status.patient.id} status={status} alerts={data.alerts} />)}</div>}
            {!loading && !error && data && data.patients.length > 0 && <div className="border-t border-slate-100 px-4 py-3 text-xs text-slate-500">{data.patients.length} patients · Select a patient to review telemetry</div>}
          </Card>
        </section>
        <aside aria-label="Shift handoff summary">
          {loading ? <Card><div className="py-8 text-center text-sm text-slate-600" role="status">Loading shift handoff…</div></Card>
            : error ? <Card><p className="text-sm font-semibold text-red-800">Unable to load shift handoff</p><p className="mt-1 text-sm text-red-800">{error}</p></Card>
              : data ? <HandoffPanel handoff={data.handoff} patients={data.patients} /> : <Card><p className="text-sm text-slate-600">No handoff data available.</p></Card>}
        </aside>
      </div>
    </AppShell>
  );
}
