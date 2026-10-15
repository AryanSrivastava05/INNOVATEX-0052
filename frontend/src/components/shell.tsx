import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useLiveUpdates } from "./LiveUpdates";
import { DemoControls } from "./DemoControls";
import { DisclaimerFooter, SimulatedBanner } from "./ui";

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { connected, polling } = useLiveUpdates();
  const isPatient = location.pathname.startsWith("/patients/");
  return (
    <div className="min-h-screen bg-background text-on-surface">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            {isPatient && (
              <Link to="/" aria-label="Back to overview" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100">
                <span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>
              </Link>
            )}
            <Link to="/" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-white" aria-label="PulseCare AI overview">
              <span className="material-symbols-outlined" aria-hidden="true">monitor_heart</span>
            </Link>
            <div className="min-w-0">
              <p className="truncate text-base font-semibold text-on-surface">PulseCare AI</p>
              <p className="truncate text-xs text-slate-500">{isPatient ? "Patient telemetry detail" : "Remote monitoring overview"}</p>
            </div>
          </div>
          <span className={`inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${connected ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
            <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-600" : "bg-amber-500"}`} />
            {connected ? "Live stream" : polling ? "Polling fallback" : "Connecting"}
          </span>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <SimulatedBanner />
        {children}
        <DisclaimerFooter />
      </main>
      <DemoControls />
    </div>
  );
}
