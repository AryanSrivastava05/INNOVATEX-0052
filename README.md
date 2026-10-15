# INNOVATEX-0052

## AS-03 Remote Patient Monitoring Backend

A FastAPI prototype for a transparent, self-prioritizing remote patient monitoring review queue. All patient data is synthetic. Thresholds are illustrative demo values, and the score is a prioritization aid, not a validated risk probability. This is decision support only, not a diagnosis.

## Setup

Requirements: Python 3.11.

From the repository root, create and activate a virtual environment, then install the backend dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend\.env` as needed. Set a non-empty `DEMO_TOKEN` before using the admin tick or scenario endpoints. Start the API from the `backend` directory:

```powershell
Set-Location backend
python -m uvicorn app.main:app --reload
```

Check the service:

```powershell
curl.exe http://127.0.0.1:8000/api/health
```

Run tests from the `backend` directory:

```powershell
python -m pytest -q
```

## Deploy

### API on Render

1. Create a Render Blueprint from this repository using the root [`render.yaml`](./render.yaml).
2. Set the generated `DEMO_TOKEN` in the Render service environment. Render generates it when the Blueprint creates the service.
3. Set `FRONTEND_ORIGIN` to the exact Vercel production origin, for example `https://pulsecare-demo.vercel.app`. For multiple deployed origins, use a comma-separated list of exact origins with no paths, e.g. `https://pulsecare-demo.vercel.app,https://pulsecare-preview.vercel.app`.
4. Deploy and verify `https://<render-service>.onrender.com/api/health`.

Render runs the simulator and keeps its readings and audit trail in memory. Restarting or sleeping the service resets this synthetic demo state. The free Render plan may sleep after inactivity.

### Frontend on Vercel

1. Import the same repository into Vercel and set **Root Directory** to `frontend`.
2. Set these Vercel project environment variables for Production (and Preview if needed):
   - `VITE_API_URL=https://<render-service>.onrender.com` (origin only; omit `/api`)
   - `VITE_DEMO_TOKEN=<the same value as Render DEMO_TOKEN>`
3. Deploy. Vercel uses `frontend/vercel.json` to route browser-side React Router paths back to the SPA.
4. Add each Vercel origin that needs API access to Render's comma-separated `FRONTEND_ORIGIN`, then redeploy the Render service if its environment changed.

`VITE_DEMO_TOKEN` is bundled into browser code so it is visible to users. It is suitable only for this synthetic demo; do not use this design for privileged or production data.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TICK_SECONDS` | `5` | Interval between background simulator ticks |
| `WEBHOOK_URL` | empty | Webhook for new critical alerts and escalations; empty disables notifications |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Comma-separated exact browser origins allowed by CORS |
| `ESCALATION_SECONDS` | `60` | Seconds before an unacknowledged critical alert escalates |
| `DEMO_TOKEN` | empty | Required `X-Demo-Token` for manual tick and scenario-trigger endpoints |
| `GROQ_API_KEY` | empty | Optional Groq key for `GET /api/handoff?ai=true`; keep private in `.env` |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq chat-completions model |
| `GROQ_TIMEOUT_SECONDS` | `10` | Groq request timeout |
| `STALE_SECONDS` | `30` | Age after which a reading is considered stale |
| `TREND_WINDOW` | `5` | SpO2 readings used by the declining-trend rule |
| `SPO2_WARNING` | `92` | Illustrative SpO2 warning threshold |
| `SPO2_CRITICAL` | `90` | Illustrative SpO2 critical threshold |
| `HEART_RATE_WARNING_HIGH` | `110` | Illustrative high heart-rate warning threshold |
| `HEART_RATE_WARNING_LOW` | `50` | Illustrative low heart-rate warning threshold |
| `HEART_RATE_CRITICAL_HIGH` | `130` | Illustrative high heart-rate critical threshold |
| `HEART_RATE_CRITICAL_LOW` | `40` | Illustrative low heart-rate critical threshold |
| `SYSTOLIC_BP_WARNING_HIGH` | `160` | Illustrative high systolic BP warning threshold |
| `SYSTOLIC_BP_WARNING_LOW` | `95` | Illustrative low systolic BP warning threshold |
| `SYSTOLIC_BP_CRITICAL_HIGH` | `180` | Illustrative high systolic BP critical threshold |
| `SYSTOLIC_BP_CRITICAL_LOW` | `85` | Illustrative low systolic BP critical threshold |

Secrets belong only in the untracked `backend\.env`; `backend\.env.example` contains safe defaults.

## API endpoints

All timestamps are ISO-8601 UTC. Responses containing vitals include `simulated: true`. Errors use `{"error": "...", "detail": "..."}`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/health` | Service status and safety disclaimer |
| `GET` | `/api/dashboard?filter=all&q=` | Patients ranked by score; filter by `all`, `needs_review`, or `acknowledged`, and optionally search patient ID/name |
| `GET` | `/api/patients/{id}` | Patient profile, latest reading, active alerts |
| `GET` | `/api/patients/{id}/history?limit=100` | Readings and alerts in time order |
| `GET` | `/api/alerts?status=active` | Alerts ranked by patient priority; status may be active, acknowledged, escalated, or resolved |
| `GET` | `/api/alerts/{id}?ai=false` | Alert detail; opt in to a cached plain-language explanation with `ai=true` |
| `POST` | `/api/alerts/{id}/acknowledge` | Acknowledge an alert; optional JSON body `{"note":"..."}` |
| `POST` | `/api/simulation/tick` | Advance simulation by one tick; requires `X-Demo-Token` |
| `POST` | `/api/scenarios/{name}?patient_id=P003` | Trigger a scenario; requires `X-Demo-Token` |
| `GET` | `/api/scenarios` | List supported scenarios |
| `GET` | `/api/config/thresholds` | Illustrative demo thresholds |
| `GET` | `/api/handoff?window_minutes=60&ai=false` | SBAR handoff JSON and template text; optional Groq polishing |
| `GET` | `/api/audit?limit=50` | Recent in-memory audit events |
| `GET` | `/api/stream` | Server-Sent Events: `tick`, `alert`, and `ranking` |

Example scenario trigger:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/scenarios/tachycardia?patient_id=P002" `
  -H "X-Demo-Token: $env:DEMO_TOKEN"
```

## 90-second demo script

1. Open the dashboard: show 12 patients with the `SIMULATED DATA` label, mostly Routine.
2. Show P008's SpO2 drifting down: the trend alert fires before the 92 threshold, with the five readings as evidence.
3. Trigger `tachycardia` on P002 via Scenario Director: show the threshold alert, P002 rising to the top, and the score breakdown.
4. Show P011's sensor dropout: `signal_lost` is raised rather than treating missing data as normal.
5. Show a webhook notification arriving in Discord/Telegram if `WEBHOOK_URL` is configured.
6. Acknowledge an alert with a note and show the status change.
7. Open the shift handoff summary and show its SBAR text.
8. Close with the limitations statement:

> All data is simulated. Thresholds are illustrative demo values and need clinician review. The score is a transparent prioritization aid, not a validated risk probability. The system supports, and does not replace, clinical judgment.
