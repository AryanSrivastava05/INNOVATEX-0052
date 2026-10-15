import { useEffect, useState } from "react";
import { ApiError, getScenarios, postScenario } from "../api/client";
import type { ScenarioResponse } from "../api/types";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? `${error.error}: ${error.detail}` : error instanceof Error ? error.message : "An unexpected error occurred.";
}

export function DemoControls() {
  const [open, setOpen] = useState(false);
  const [patientId, setPatientId] = useState("P008");
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ScenarioResponse | null>(null);

  useEffect(() => {
    if (!open || scenarios.length > 0) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    getScenarios().then((response) => {
      if (!cancelled) setScenarios(response.scenarios);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(errorMessage(reason));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [open, scenarios.length]);

  async function runScenario(name: string) {
    if (!patientId.trim()) {
      setError("Enter a patient ID before running a scenario.");
      return;
    }
    setPending(name);
    setError("");
    setResult(null);
    try {
      const response = await postScenario(name, patientId.trim());
      setResult(response);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 flex w-[min(22rem,calc(100vw-2rem))] flex-col items-end gap-2">
      {open && (
        <section id="demo-controls-panel" className="max-h-[min(70vh,36rem)] w-full overflow-y-auto rounded-lg border border-slate-300 bg-white p-4" aria-labelledby="demo-controls-heading">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="demo-controls-heading" className="text-sm font-semibold">Demo controls</h2>
              <p className="mt-1 text-xs text-slate-500">Trigger synthetic events on a patient.</p>
            </div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close demo controls" className="rounded p-1 text-slate-500 hover:bg-slate-100">
              <span className="material-symbols-outlined text-base" aria-hidden="true">close</span>
            </button>
          </div>
          <label className="mt-4 block text-xs font-semibold text-slate-700" htmlFor="scenario-patient">Patient ID</label>
          <input id="scenario-patient" value={patientId} onChange={(event) => setPatientId(event.target.value)} className="mt-1 h-9 w-full rounded border border-slate-300 px-2.5 text-sm" placeholder="P001" />
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-600">Scenarios</h3>
          {loading ? <p className="mt-2 text-sm text-slate-600" role="status">Loading scenarios…</p>
            : error && scenarios.length === 0 ? <p className="mt-2 text-sm text-red-800" role="alert">{error}</p>
              : scenarios.length === 0 ? <p className="mt-2 text-sm text-slate-600">No scenarios are available.</p>
                : <div className="mt-2 grid grid-cols-1 gap-2">
                  {scenarios.map((scenario) => (
                    <button key={scenario} type="button" onClick={() => runScenario(scenario)} disabled={pending !== null} className="flex min-h-9 items-center justify-between gap-2 rounded border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                      <span>{scenario.replace(/_/g, " ")}</span>
                      <span className="material-symbols-outlined text-base text-primary" aria-hidden="true">{pending === scenario ? "progress_activity" : "play_arrow"}</span>
                    </button>
                  ))}
                </div>}
          {error && scenarios.length > 0 && <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-900" role="alert">{error}</p>}
          {result && <p className="mt-3 rounded border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-900" role="status">
            {result.scenario.replace(/_/g, " ")} triggered for {result.patient_id}. Latest reading updated.
          </p>}
        </section>
      )}
      <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="demo-controls-panel" className="inline-flex min-h-11 items-center gap-2 rounded-full border border-primary bg-white px-4 py-2 text-sm font-semibold text-primary">
        <span className="material-symbols-outlined text-base" aria-hidden="true">tune</span>
        Demo controls
      </button>
    </div>
  );
}
