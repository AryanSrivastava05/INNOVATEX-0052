import type { ReactNode } from "react";
import type { AlertStatus, RiskBand } from "../api/types";

type PillStatus = RiskBand | AlertStatus | "Normal" | "Warning" | "Critical" | "Stale" | "No signal";

const pillStyles: Record<PillStatus, string> = {
  High: "border-red-200 bg-red-50 text-red-800",
  Medium: "border-amber-200 bg-amber-50 text-amber-800",
  Routine: "border-emerald-200 bg-emerald-50 text-emerald-800",
  active: "border-amber-200 bg-amber-50 text-amber-800",
  acknowledged: "border-blue-200 bg-blue-50 text-blue-800",
  escalated: "border-red-200 bg-red-50 text-red-800",
  resolved: "border-slate-200 bg-slate-100 text-slate-700",
  Normal: "border-emerald-200 bg-emerald-50 text-emerald-800",
  Warning: "border-amber-200 bg-amber-50 text-amber-800",
  Critical: "border-red-200 bg-red-50 text-red-800",
  Stale: "border-amber-200 bg-amber-50 text-amber-800",
  "No signal": "border-red-200 bg-red-50 text-red-800",
};

export function StatusPill({ status }: { status: PillStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${pillStyles[status]}`}>
      {status}
    </span>
  );
}

export function PriorityBadge({ band, score }: { band: RiskBand; score?: number }) {
  const styles: Record<RiskBand, string> = {
    High: "border-red-200 bg-red-50 text-red-800",
    Medium: "border-amber-200 bg-amber-50 text-amber-800",
    Routine: "border-slate-200 bg-slate-100 text-slate-700",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[band]}`}>
      {band}{score !== undefined && <span className="tabular-nums">{score}</span>}
    </span>
  );
}

export interface VitalCardProps {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  threshold?: string;
  status: "normal" | "warning" | "critical" | "stale" | "missing";
  icon: string;
}

export function VitalCard({ label, value, unit, threshold, status, icon }: VitalCardProps) {
  const statusText = {
    normal: "Within demo threshold",
    warning: "Outside demo threshold",
    critical: "Critical demo threshold",
    stale: "Reading is stale",
    missing: "No reading available",
  }[status];
  const accent = status === "critical" ? "border-l-error" : status === "warning" || status === "stale" ? "border-l-amber-500" : "border-l-primary";
  return (
    <section className={`rounded-lg border border-slate-200 border-l-4 ${accent} bg-white p-4`}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-600">
          <span className="material-symbols-outlined text-base text-primary" aria-hidden="true">{icon}</span>
          {label}
        </h3>
        {status !== "normal" && <StatusPill status={status === "missing" ? "No signal" : status === "critical" ? "Critical" : status === "warning" ? "Warning" : "Stale"} />}
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className={`text-3xl font-semibold tracking-tight tabular-nums ${status === "missing" || status === "stale" ? "text-slate-400" : "text-on-surface"}`}>
          {value == null ? "—" : value}
        </span>
        {unit && value != null && <span className="text-sm text-slate-500">{unit}</span>}
      </div>
      <div className="mt-3 flex flex-wrap justify-between gap-2 border-t border-slate-100 pt-2 text-xs">
        <span className="text-slate-500">{threshold || "Illustrative demo thresholds"}</span>
        <span className={`font-medium ${status === "critical" ? "text-error" : status === "warning" || status === "stale" ? "text-amber-700" : status === "missing" ? "text-error" : "text-tertiary"}`}>
          {statusText}
        </span>
      </div>
    </section>
  );
}

export function SimulatedBanner() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-slate-700" role="note">
      <span className="material-symbols-outlined text-base text-primary" aria-hidden="true">info</span>
      <span><strong className="mr-2 text-primary">SIMULATED DATA</strong>Alerts support review and do not replace medical judgment.</span>
    </div>
  );
}

export function DisclaimerFooter() {
  return (
    <footer className="rounded-lg border border-slate-200 bg-surface-container-low px-4 py-3 text-center">
      <p className="text-xs font-semibold uppercase tracking-wider text-primary">Decision support only. Not a diagnosis.</p>
      <p className="mt-1 text-xs leading-relaxed text-slate-600">All patient data and thresholds are synthetic and for demonstration only. Clinical review is required.</p>
    </footer>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`}>{children}</section>;
}

export function InitialsAvatar({ name, className = "" }: { name: string; className?: string }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("");
  return (
    <span className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary-fixed text-sm font-semibold text-on-primary-fixed ${className}`} aria-label={`${name} initials`}>
      {initials || "?"}
    </span>
  );
}
