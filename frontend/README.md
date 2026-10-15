# PulseCare AI frontend

Synthetic remote-monitoring review dashboard for AS-03. This interface is decision support only, not a diagnosis; all patient readings and thresholds are illustrative demo data.

## Run locally

Requirements: Node.js 20 or later and the AS-03 FastAPI backend.

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env.local
```

Set the values in `frontend\.env.local`, then start the backend and frontend in separate terminals:

```powershell
# Terminal 1: from the repository root
Set-Location backend
python -m uvicorn app.main:app --reload
```

```powershell
# Terminal 2: from the repository root
Set-Location frontend
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`). Configure the backend's `FRONTEND_ORIGIN` to that same origin if it differs from the backend default.

## Environment variables

| Variable | Example | Purpose |
| --- | --- | --- |
| `VITE_API_URL` | `http://127.0.0.1:8000` | Backend origin. The frontend appends `/api`; do not add `/api` here. |
| `VITE_DEMO_TOKEN` | `your-demo-token` | Sent as `X-Demo-Token` for simulation tick and scenario requests. It must match the backend's `DEMO_TOKEN`. |

`VITE_DEMO_TOKEN` is a browser-visible demo credential, not a production secret. Keep it out of committed files; use the ignored `.env.local`. If it is unset or does not match the backend token, protected demo controls display the backend error.

## Features

- Overview queue with server-side search and review filters, priority bands, latest telemetry, and shift handoff.
- Patient detail with API-configured demo thresholds, active alert evidence, score breakdown, trend history, and audit events.
- Named SSE updates (`tick`, `alert`, and `ranking`) with a five-second polling fallback when the stream is unavailable.
- Demo scenario controls for `spo2_decline`, `tachycardia`, `bp_spike`, `sensor_dropout`, and `recovery`.
- Provider notes are saved only in the current browser. Alert acknowledgements and simulation actions use the backend API.

## Production build

```powershell
Set-Location frontend
npm run build
npm run preview
```

## Deploy

### Vercel

1. Import the repository and set the Vercel **Root Directory** to `frontend`.
2. Set `VITE_API_URL` to the Render API origin (for example, `https://pulsecare-ai-api.onrender.com`), without a trailing slash or `/api`.
3. Set `VITE_DEMO_TOKEN` to the same demo token configured on the Render backend.
4. Deploy. `vercel.json` sends browser routes such as `/patients/P008` to the React application.

The Vite environment variables are embedded in the public client bundle. `VITE_DEMO_TOKEN` is only a demo gate for synthetic simulation endpoints; it is not a secret.

### Connect the Render API

In the Render API service, set `FRONTEND_ORIGIN` to the exact Vercel origin (scheme and host only). Multiple allowed production/preview origins can be comma-separated. See the repository README for Blueprint deployment details.
