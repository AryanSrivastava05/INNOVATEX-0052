import { createContext, useContext, useEffect, useRef, useState } from "react";
import { connectToEventStream } from "../api/client";
import type { ReactNode } from "react";

interface LiveUpdatesValue {
  revision: number;
  connected: boolean;
  polling: boolean;
  toast: string | null;
  dismissToast: () => void;
}

const LiveUpdatesContext = createContext<LiveUpdatesValue | null>(null);

export function LiveUpdatesProvider({ children }: { children: ReactNode }) {
  const [revision, setRevision] = useState(0);
  const [connected, setConnected] = useState(false);
  const [polling, setPolling] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const seenCriticalAlerts = useRef(new Set<string>());

  useEffect(() => {
    let fallback: number | undefined;
    let refreshDebounce: number | undefined;
    let dismissTimer: number | undefined;
    const refresh = () => setRevision((current) => current + 1);
    const stopFallback = () => {
      if (fallback !== undefined) window.clearInterval(fallback);
      fallback = undefined;
    };
    const close = connectToEventStream((event) => {
      if (event.type === "alert" && event.data.severity === "critical") {
        const alertId = typeof event.data.alert_id === "string" ? event.data.alert_id : undefined;
        if (alertId && !seenCriticalAlerts.current.has(alertId)) {
          seenCriticalAlerts.current.add(alertId);
          const patientId = typeof event.data.patient_id === "string" ? event.data.patient_id : "Patient";
          const alertType = typeof event.data.type === "string" ? event.data.type.replace(/_/g, " ") : "critical alert";
          setToast(`New critical alert · ${patientId} · ${alertType}`);
          if (dismissTimer !== undefined) window.clearTimeout(dismissTimer);
          dismissTimer = window.setTimeout(() => setToast(null), 8000);
        }
      }
      if (refreshDebounce !== undefined) window.clearTimeout(refreshDebounce);
      refreshDebounce = window.setTimeout(refresh, 250);
    }, () => {
      setConnected(false);
      setPolling(true);
      if (fallback === undefined) fallback = window.setInterval(refresh, 5000);
    }, () => {
      setConnected(true);
      setPolling(false);
      stopFallback();
    });
    return () => {
      close();
      stopFallback();
      if (refreshDebounce !== undefined) window.clearTimeout(refreshDebounce);
      if (dismissTimer !== undefined) window.clearTimeout(dismissTimer);
    };
  }, []);

  return (
    <LiveUpdatesContext.Provider value={{ revision, connected, polling, toast, dismissToast: () => setToast(null) }}>
      {children}
      {toast && (
        <div className="fixed right-4 top-4 z-50 flex max-w-sm items-start gap-3 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900" role="alert">
          <span className="material-symbols-outlined text-error" aria-hidden="true">priority_high</span>
          <p className="flex-1 font-semibold">{toast}</p>
          <button type="button" onClick={() => setToast(null)} aria-label="Dismiss alert toast" className="text-red-700">
            <span className="material-symbols-outlined text-base" aria-hidden="true">close</span>
          </button>
        </div>
      )}
    </LiveUpdatesContext.Provider>
  );
}

export function useLiveUpdates(): LiveUpdatesValue {
  const context = useContext(LiveUpdatesContext);
  if (!context) throw new Error("useLiveUpdates must be used within LiveUpdatesProvider");
  return context;
}
