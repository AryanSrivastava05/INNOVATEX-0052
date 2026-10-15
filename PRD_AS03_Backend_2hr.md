# PRD: AS-03 AI-Based Remote Patient Monitoring: Backend (2-Hour Prototype)

**Version:** 2.0 (backend-focused, 2-hour build)
**Audience:** Hackathon judges, backend developer, GitHub Copilot
**Data:** 100% synthetic. Decision support only. Not diagnostic.
**Split:** Backend and automations (this doc). Teammate builds the UI against the API contract in section 8.

---

## 1. Vision

An explainable, self-prioritizing review queue for remote patient monitoring. The backend simulates patients, detects threshold breaches and worsening trends, explains every alert, ranks patients transparently, and pushes alerts out through automations.

**Pitch line:** "Not just a vitals display. A review queue that tells you who to look at first, why, and what changed since last shift."

## 2. Scope for 2 hours

**Must ship (P0)**: simulator, threshold alerts, SpO2 trend alert, dedupe, priority score, ack + note, scenarios, live stream, tests.
**Should ship (P1, standout)**: shift handoff summary, webhook automation, signal-quality alerts, escalation.
**Stretch (P2)**: baseline-deviation advisory (z-score), Isolation Forest, SQLite persistence.

Cut anything in P2 first. A complete P0 + two P1 features beats a half-working everything.

## 3. Standout features (the differentiators)

| # | Feature | Why judges care | Effort |
|---|---------|-----------------|--------|
| 1 | **Scenario Director**: `POST /api/scenarios/{name}` triggers reproducible events (`spo2_decline`, `tachycardia`, `bp_spike`, `sensor_dropout`, `recovery`) on any patient | Judges can trigger a live event on demand. Deterministic and repeatable | Low |
| 2 | **Explainable score breakdown**: every patient returns `score_breakdown` with each contributing factor and points | Transparent, not a black box | Low |
| 3 | **Shift Handoff Summary**: `GET /api/handoff` returns an SBAR-style, template-generated summary: who is new, worsening, resolved, unacknowledged | Real clinical workflow value; looks impressive | Medium |
| 4 | **Alert Fan-out Webhook**: new High alerts POST to a configurable webhook (n8n / Discord / Telegram) | Shows automation skills; works outside the dashboard | Low |
| 5 | **Signal Quality Guard**: missing or stale readings raise a `signal_lost` alert instead of being treated as normal | Directly satisfies the PRD requirement; shows safety thinking | Low |
| 6 | **Escalation timer**: an unacknowledged critical alert past N seconds (demo time) is marked `escalated` and score bonus applied | Fights alert fatigue and missed alerts | Low |
| 7 | **Live stream (SSE)**: `GET /api/stream` pushes tick, alert, and ranking events | Real-time without polling; frontend gets it in about 10 lines | Low |
| 8 | **Audit trail**: `GET /api/audit` logs ticks, alert create/update, ack, scenario triggers | Accountability story | Low |

## 4. Tech stack (backend)

- Python 3.11+, FastAPI, Pydantic v2, Uvicorn
- In-memory store (dicts + deque) behind a repository interface so SQLite can drop in later
- pytest + httpx for tests
- Optional: pandas, scikit-learn (P2 only)
- Config via `.env` (`.env.example` committed): `TICK_SECONDS`, `WEBHOOK_URL`, `FRONTEND_ORIGIN`, `ESCALATION_SECONDS`, `DEMO_TOKEN`

### Folder structure

```
backend/
  app/
    main.py            # FastAPI app, CORS, routers, startup
    config.py          # settings from env
    models.py          # Pydantic models
    store.py           # in-memory repository
    simulator.py       # patients, tick(), scenarios
    rules.py           # thresholds, trend, signal quality
    scoring.py         # priority score + risk band
    alerts.py          # create/update/dedupe/escalate/ack
    handoff.py         # shift summary generator
    notifier.py        # webhook fan-out (non-blocking, failure-safe)
    routes/
      dashboard.py  patients.py  alerts.py  simulation.py  stream.py  misc.py
  tests/
    test_rules.py  test_trend.py  test_dedupe.py  test_scoring.py  test_api.py
  .env.example
  requirements.txt
```

## 5. Data models

```python
class Reading:      patient_id, ts (datetime UTC), hr:int|None, sys_bp:int|None, dia_bp:int|None, spo2:int|None, quality: "ok"|"missing"|"stale"
class Patient:      id ("P001"), name (synthetic), age, scenario: str|None
class Alert:        id, patient_id, type, metric, observed, threshold, severity ("warning"|"critical"),
                    kind ("threshold"|"trend"|"signal"|"advisory"), explanation, evidence: list[Reading],
                    status ("active"|"acknowledged"|"escalated"|"resolved"),
                    created_at, updated_at, acknowledged_at|None, ack_note|None, occurrences:int
class PatientStatus: patient, latest, risk_band, score, score_breakdown: list[{factor, points, reason}],
                    active_alert_count, data_freshness_seconds, simulated: true
```

Alert dedupe key: `(patient_id, type)`.

## 6. Rules (all demo-only, configurable, labeled illustrative)

**Thresholds** (`GET /api/config/thresholds`):

| Metric | Warning | Critical |
|--------|---------|----------|
| SpO2 | < 92 | < 90 |
| Heart rate | > 110 or < 50 | > 130 or < 40 |
| Systolic BP | > 160 or < 95 | > 180 or < 85 |

**Trend (SpO2):** over the last `N=5` readings (configurable), if each value is lower than or equal to the previous and total drop is at least 3 points, raise `spo2_decline` (warning), even if the latest value is above the low threshold. Evidence = the 5 readings.

**Repeated abnormal:** 3 consecutive abnormal readings on the same metric raises a persistence flag (feeds the score; severity bumps one level).

**Signal quality:** if the latest reading is missing, or older than `STALE_SECONDS` (default 30), raise `signal_lost` (warning). Never treat missing as normal.

**Dedupe:** if an active/escalated alert exists for `(patient_id, type)`, update `observed`, `updated_at`, `occurrences += 1`, and re-evaluate severity. Do not create a new one. If the alert was `acknowledged` and the condition persists, reopen it as `active` (note "reopened").

**Auto-resolve:** after 3 consecutive normal readings, mark the alert `resolved`.

**Advisory (P2):** rolling baseline z-score above 3 gives `kind="advisory"` with the text "Unusual compared with this patient's recent baseline". Never an emergency alert by itself. If it errors, rules continue.

## 7. Priority score (transparent, not a clinical probability)

```
score = sum of:
  severity:    +40 per critical active alert, +20 per warning
  persistence: +3 per consecutive abnormal reading (cap 15)
  trend:       +15 if a trend alert is active
  signal:      +10 if signal_lost
  escalation:  +15 if any alert is escalated
  advisory:    +5 if ML/baseline advisory present
Bands: High >= 50, Medium >= 20, Routine < 20
```

Every point is returned in `score_breakdown` with a human-readable reason. Sort descending by score, tie-break by oldest unacknowledged alert.

## 8. API contract (share this with your UI teammate first)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | status, version, `simulated: true` |
| GET | `/api/dashboard?filter=all\|needs_review\|acknowledged&q=` | patients sorted by score, with latest vitals, band, breakdown, alert count |
| GET | `/api/patients/{id}` | profile, latest reading, active alerts |
| GET | `/api/patients/{id}/history?limit=100` | readings in time order, alerts marked on the timeline |
| GET | `/api/alerts?status=active` | alert queue ordered by priority |
| POST | `/api/alerts/{id}/acknowledge` | body `{note?: str}`, sets status and `acknowledged_at` |
| POST | `/api/simulation/tick` | advance one step (admin) |
| POST | `/api/scenarios/{name}?patient_id=P003` | trigger a scenario |
| GET | `/api/scenarios` | list available scenarios |
| GET | `/api/config/thresholds` | active demo thresholds |
| GET | `/api/handoff` | shift handoff summary (JSON + `text`) |
| GET | `/api/audit?limit=50` | audit trail |
| GET | `/api/stream` | SSE: events `tick`, `alert`, `ranking` |

Rules for responses: ISO-8601 UTC timestamps, consistent error shape `{"error": "...", "detail": "..."}`, CORS only for `FRONTEND_ORIGIN`, every payload that includes vitals carries `simulated: true`. Admin endpoints (`tick`, `scenarios`) require header `X-Demo-Token` matching `DEMO_TOKEN`.

## 9. Simulator

- Seed 12 patients (`P001` to `P012`, fake names), 30 readings of history each, baseline vitals with small seeded noise (`random.Random(42)`).
- Background task ticks every `TICK_SECONDS` (default 5). After each tick: run rules, update alerts, recompute scores, emit SSE events, call notifier.
- Default demo state (deterministic): P001-P007 normal, P008 slow SpO2 decline starting at tick 5, P009 tachycardia breach, P010 BP spike, P011 sensor dropout, P012 recovering.
- Scenarios override a patient's generator for the next N ticks. `recovery` returns vitals to baseline.

## 10. Shift handoff summary

`GET /api/handoff?window_minutes=60` returns:

```json
{
  "generated_at": "...",
  "simulated": true,
  "new_alerts": [], "worsening": [], "resolved": [], "unacknowledged": [],
  "text": "SBAR-style plain text..."
}
```

Template-based, no LLM required. Format: Situation (counts), Background (who is High risk and why), Assessment (trends in the window), Review needed (unacknowledged items). Optional P2: pass the JSON to an LLM for a nicer paragraph, with the template as fallback.

## 11. Automation: alert fan-out

`notifier.py` POSTs a JSON payload `{patient_id, severity, metric, observed, threshold, explanation, ts, simulated: true}` to `WEBHOOK_URL` when a **new** critical alert is created or an alert is escalated. Run in a background task with a 3s timeout; failures are logged and never block monitoring. If `WEBHOOK_URL` is empty, do nothing. Works directly with n8n, Make, Discord, or a Telegram relay.

## 12. Safety and labeling

- Every response that carries vitals includes `simulated: true`; health endpoint and handoff text include "Decision support only. Not a diagnosis."
- No real data, no secrets in code, `.env` excluded from Git.
- Thresholds labeled demo-only; real use requires clinician review.
- ML/baseline signals are advisory only. Never claim prediction of emergencies or improved outcomes.

## 13. Tests (required before demo)

- `test_rules.py`: each threshold boundary (91 vs 92, 89 vs 90, HR and BP edges)
- `test_trend.py`: declining SpO2 above threshold triggers; flat or noisy series does not
- `test_dedupe.py`: 10 breaching ticks produce 1 alert with `occurrences == 10`; ack then persist reopens it
- `test_scoring.py`: critical outranks warning; persistence and escalation raise score; tie-break works
- `test_api.py`: dashboard sorted, ack changes status, missing data gives `signal_lost`, bad token gives 401

## 14. 2-hour plan

| Time | Milestone | Done when |
|------|-----------|-----------|
| 0:00-0:15 | Skeleton, config, models, `/api/health`, CORS, share API contract with teammate | `curl /api/health` works |
| 0:15-0:35 | Store + simulator + seeded patients + `/dashboard`, `/patients`, `/history`, tick loop | 12 patients update live |
| 0:35-1:00 | Rules, dedupe, auto-resolve, signal quality, alerts endpoints, ack | Scenario breach creates one alert |
| 1:00-1:15 | Scoring + score breakdown + sorting | High-risk patient rises to top |
| 1:15-1:30 | Scenario Director + SSE stream + audit | Judge can trigger and watch live |
| 1:30-1:45 | Handoff summary + webhook notifier + escalation | Webhook fires on critical |
| 1:45-2:00 | Tests, README with demo script, rehearse | `pytest` green, demo runs end to end |

If you fall behind, drop in this order: escalation, webhook, handoff, audit. Never drop tests for dedupe and scoring.

## 15. Demo script (90 seconds)

1. Open dashboard: 12 patients, `SIMULATED DATA` label, mostly Routine.
2. P008 SpO2 drifting down: trend alert fires before the 92 threshold, evidence shows the 5 readings.
3. Trigger `tachycardia` on P002 via Scenario Director: threshold alert, patient jumps to top, score breakdown shown.
4. P011 dropout: `signal_lost`, not shown as normal.
5. Webhook ping arrives in Discord/Telegram.
6. Acknowledge with a note, status changes.
7. Open handoff summary: one-page SBAR text.
8. Close with the limitations statement.

## 16. GitHub Copilot workflow

Work one milestone at a time. Open this file in the editor so Copilot Chat uses it as context, and start each session with: *"Read PRD_AS03_Backend_2hr.md. We are on milestone X. Inspect existing files first, summarize what you will change, then implement. Do not touch other milestones."*

**Prompts, in order:**

1. **Skeleton:** "Create the FastAPI project in backend/ following the folder structure in section 4. Implement config.py (env settings with pydantic-settings), models.py (section 5), and GET /api/health returning status, version and simulated=true. Add CORS limited to FRONTEND_ORIGIN, requirements.txt and .env.example."
2. **Simulator:** "Implement store.py (in-memory repository with deque history per patient) and simulator.py per section 9: 12 seeded patients with random.Random(42), 30 history readings each, a tick() function, and a background asyncio task. Add GET /api/dashboard, /api/patients/{id}, /api/patients/{id}/history and POST /api/simulation/tick with X-Demo-Token."
3. **Rules and alerts:** "Implement rules.py (thresholds, SpO2 trend, repeated abnormal, signal quality) and alerts.py (create/update/dedupe by patient_id+type, reopen after ack, auto-resolve after 3 normal readings) exactly as in section 6. Add GET /api/alerts and POST /api/alerts/{id}/acknowledge. Write tests in tests/test_rules.py, test_trend.py, test_dedupe.py."
4. **Scoring:** "Implement scoring.py per section 7 returning score, band and score_breakdown with reasons. Sort the dashboard and alerts by it. Write tests/test_scoring.py."
5. **Scenarios, stream, audit:** "Add scenario definitions to simulator.py (spo2_decline, tachycardia, bp_spike, sensor_dropout, recovery), POST /api/scenarios/{name}, GET /api/scenarios, an audit log with GET /api/audit, and GET /api/stream using Server-Sent Events emitting tick, alert and ranking events."
6. **Handoff and notifier:** "Implement handoff.py per section 10 (template-based SBAR text plus JSON) and notifier.py per section 11 using httpx with a 3s timeout and failure-safe background execution. Add escalation after ESCALATION_SECONDS for unacknowledged critical alerts."
7. **Finish:** "Write tests/test_api.py per section 13, run pytest, fix failures, then write README.md with setup steps, env vars, endpoint table and the demo script from section 15."

**Rules for Copilot:** require tests for every rule; keep schemas identical to section 5 and 8; synthetic data only; never invent clinical claims; run the app and tests after every milestone before moving on; secrets stay in `.env`.

## 17. Definition of done

Run `uvicorn app.main:app --reload`, see 12 patients updating live, trigger a scenario, watch one explained alert appear (no duplicates), see that patient rise to the top with a score breakdown, receive the webhook, acknowledge with a note, generate the handoff summary, and have `pytest` pass.

## 18. Limitations statement (say this at the end of the demo)

All data is simulated. Thresholds are illustrative demo values and need clinician review. The score is a transparent prioritization aid, not a validated risk probability. The system supports, and does not replace, clinical judgment.
