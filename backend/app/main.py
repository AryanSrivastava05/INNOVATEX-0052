import asyncio
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Literal

from fastapi import FastAPI
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.alerts import AlertManager
from app.models import (
    AcknowledgeRequest,
    AuditResponse,
    AlertListResponse,
    AlertResponse,
    DashboardResponse,
    HandoffResponse,
    HealthResponse,
    PatientHistoryResponse,
    PatientProfileResponse,
    PatientStatus,
    Reading,
    ScenarioListResponse,
    ScenarioResponse,
    SimulationTickResponse,
    ThresholdsResponse,
)
from app.events import EventHub
from app.handoff import generate_handoff
from app.rules import demo_thresholds
from app.scoring import calculate_score, sort_alerts_by_priority, sort_patients_by_priority
from app.simulator import SCENARIO_NAMES, Simulator
from app.store import InMemoryRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    repository = InMemoryRepository()
    simulator = Simulator(repository)
    simulator.seed()
    alert_manager = AlertManager(repository)
    event_hub = EventHub(repository)
    app.state.repository = repository
    app.state.simulator = simulator
    app.state.alert_manager = alert_manager
    app.state.event_hub = event_hub
    alert_manager.event_hub = event_hub
    task = asyncio.create_task(
        simulator.run(
            settings.tick_seconds,
            lambda readings: _publish_tick_events(app, readings),
        )
    )
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="AS-03 Remote Patient Monitoring API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.frontend_origin.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=app.version,
        simulated=True,
        message="Decision support only. Not a diagnosis.",
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
    error = {
        401: "unauthorized",
        404: "not_found",
    }.get(exc.status_code, "request_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error, "detail": str(exc.detail)},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": str(exc)},
    )


def verify_demo_token(
    x_demo_token: Annotated[str | None, Header()] = None,
) -> None:
    configured_token = settings.demo_token
    if (
        not configured_token
        or x_demo_token is None
        or not secrets.compare_digest(x_demo_token, configured_token)
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing demo token")


def _publish_tick_events(app: FastAPI, readings: list[Reading]) -> None:
    repository = app.state.repository
    alert_manager: AlertManager = app.state.alert_manager
    event_hub: EventHub = app.state.event_hub
    alert_manager.process_tick(readings)

    event_hub.publish(
        "tick",
        {
            "tick": app.state.simulator.tick_count,
            "patient_count": len(readings),
            "simulated": True,
        },
    )
    patients: list[PatientStatus] = []
    for patient in repository.get_patients():
        patient_alerts = repository.get_alerts(patient.id)
        score = calculate_score(
            patient_alerts,
            {
                metric: count
                for (patient_id, metric), count in alert_manager.consecutive_abnormal.items()
                if patient_id == patient.id
            },
        )
        patients.append(
            PatientStatus(
                patient=patient,
                latest=repository.get_latest_reading(patient.id),
                risk_band=score.risk_band,
                score=score.score,
                score_breakdown=score.score_breakdown,
                active_alert_count=sum(
                    alert.status in ("active", "escalated")
                    for alert in patient_alerts
                ),
                data_freshness_seconds=0,
            )
        )
    sorted_patients = sort_patients_by_priority(patients, repository.get_alerts())
    event_hub.publish(
        "ranking",
        {
            "patients": [
                {"patient_id": patient.patient.id, "score": patient.score}
                for patient in sorted_patients
            ],
            "simulated": True,
        },
    )


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(
    request: Request,
    filter: Annotated[
        Literal["all", "needs_review", "acknowledged"],
        Query(),
    ] = "all",
    q: Annotated[str, Query()] = "",
) -> DashboardResponse:
    repository = request.app.state.repository
    alert_manager: AlertManager = request.app.state.alert_manager
    patients: list[PatientStatus] = []
    for patient in repository.get_patients():
        patient_alerts = repository.get_alerts(patient.id)
        if filter == "needs_review" and not any(
            alert.status in ("active", "escalated") for alert in patient_alerts
        ):
            continue
        if filter == "acknowledged" and not any(
            alert.status == "acknowledged" for alert in patient_alerts
        ):
            continue
        if q and q.casefold() not in patient.id.casefold() and q.casefold() not in patient.name.casefold():
            continue

        latest = repository.get_latest_reading(patient.id)
        freshness = (
            max(0.0, (datetime.now(timezone.utc) - latest.ts).total_seconds())
            if latest is not None
            else 0.0
        )
        score = calculate_score(
            patient_alerts,
            {
                metric: count
                for (patient_id, metric), count in alert_manager.consecutive_abnormal.items()
                if patient_id == patient.id
            },
        )
        patients.append(
            PatientStatus(
                patient=patient,
                latest=latest,
                risk_band=score.risk_band,
                score=score.score,
                score_breakdown=score.score_breakdown,
                active_alert_count=sum(
                    alert.status in ("active", "escalated")
                    for alert in patient_alerts
                ),
                data_freshness_seconds=freshness,
            )
        )
    return DashboardResponse(
        patients=sort_patients_by_priority(patients, repository.get_alerts())
    )


@app.get("/api/patients/{patient_id}", response_model=PatientProfileResponse)
def patient_profile(patient_id: str, request: Request) -> PatientProfileResponse:
    repository = request.app.state.repository
    patient = repository.get_patient(patient_id)
    latest = repository.get_latest_reading(patient_id)
    if patient is None or latest is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    active_alerts = [
        alert
        for alert in request.app.state.alert_manager.repository.get_alerts(patient_id)
        if alert.status in ("active", "escalated")
    ]
    return PatientProfileResponse(
        patient=patient,
        latest=latest,
        active_alerts=active_alerts,
    )


@app.get("/api/patients/{patient_id}/history", response_model=PatientHistoryResponse)
def patient_history(
    patient_id: str,
    request: Request,
    limit: Annotated[int, Query(ge=1)] = 100,
) -> PatientHistoryResponse:
    repository = request.app.state.repository
    if repository.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return PatientHistoryResponse(
        patient_id=patient_id,
        readings=repository.get_readings(patient_id, limit),
        alerts=request.app.state.alert_manager.repository.get_alerts(patient_id),
    )


@app.get("/api/alerts", response_model=AlertListResponse)
def alerts(
    request: Request,
    status: Annotated[
        str,
        Query(pattern="^(active|acknowledged|escalated|resolved)$"),
    ] = "active",
) -> AlertListResponse:
    repository = request.app.state.repository
    alert_manager: AlertManager = request.app.state.alert_manager
    all_alerts = repository.get_alerts()
    patient_scores = {
        patient.id: calculate_score(
            repository.get_alerts(patient.id),
            {
                metric: count
                for (patient_id, metric), count in alert_manager.consecutive_abnormal.items()
                if patient_id == patient.id
            },
        ).score
        for patient in repository.get_patients()
    }
    return AlertListResponse(
        alerts=sort_alerts_by_priority(
            alert_manager.list_alerts(status),
            patient_scores,
            all_alerts,
        )
    )


@app.get("/api/alerts/{alert_id}", response_model=AlertResponse)
def alert_detail(
    alert_id: str,
    request: Request,
    ai: Annotated[bool, Query()] = False,
) -> AlertResponse:
    repository = request.app.state.repository
    alert = repository.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    if ai and alert.ai_explanation is None:
        from app.llm import explain_alert

        alert.ai_explanation = explain_alert(
            {
                "evidence": [
                    reading.model_dump(mode="json") for reading in alert.evidence
                ],
                "threshold": alert.threshold,
                "rule_explanation": alert.explanation,
            }
        )
        if alert.ai_explanation is not None:
            repository.update_alert(alert)

    return AlertResponse(alert=alert)


@app.post(
    "/api/alerts/{alert_id}/acknowledge",
    response_model=AlertResponse,
)
def acknowledge_alert(
    alert_id: str,
    request: Request,
    body: AcknowledgeRequest | None = None,
) -> AlertResponse:
    alert_manager: AlertManager = request.app.state.alert_manager
    alert = alert_manager.acknowledge(alert_id, body.note if body else None)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return AlertResponse(alert=alert)


@app.get("/api/config/thresholds", response_model=ThresholdsResponse)
def config_thresholds() -> ThresholdsResponse:
    return ThresholdsResponse(
        label="Illustrative demo thresholds; not for clinical use.",
        thresholds=demo_thresholds(),
    )


@app.get("/api/handoff", response_model=HandoffResponse)
def handoff(
    request: Request,
    window_minutes: Annotated[int, Query(ge=1, le=1440)] = 60,
    ai: Annotated[bool, Query()] = False,
) -> HandoffResponse:
    alert_manager: AlertManager = request.app.state.alert_manager
    result = generate_handoff(
        request.app.state.repository,
        window_minutes=window_minutes,
        consecutive_abnormal=alert_manager.consecutive_abnormal,
    )
    if ai:
        from app.llm import polish_handoff

        structured_handoff = result.model_dump(
            mode="json",
            exclude={"text", "ai_text", "ai_used"},
        )
        result.ai_text = polish_handoff(structured_handoff)
        result.ai_used = result.ai_text is not None
    return result


@app.get("/api/scenarios", response_model=ScenarioListResponse)
def scenarios() -> ScenarioListResponse:
    return ScenarioListResponse(scenarios=list(SCENARIO_NAMES))


@app.post(
    "/api/scenarios/{name}",
    response_model=ScenarioResponse,
    dependencies=[Depends(verify_demo_token)],
)
def trigger_scenario(
    name: str,
    request: Request,
    patient_id: Annotated[str, Query()],
) -> ScenarioResponse:
    simulator: Simulator = request.app.state.simulator
    try:
        duration_ticks = simulator.trigger_scenario(name, patient_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    request.app.state.event_hub.publish(
        "scenario_triggered",
        {
            "scenario": name,
            "patient_id": patient_id,
            "duration_ticks": duration_ticks,
        },
    )
    readings = simulator.tick()
    _publish_tick_events(request.app, readings)
    latest = request.app.state.repository.get_latest_reading(patient_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return ScenarioResponse(
        scenario=name,
        patient_id=patient_id,
        duration_ticks=duration_ticks,
        tick=simulator.tick_count,
        latest=latest,
    )


@app.get("/api/audit", response_model=AuditResponse)
def audit(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> AuditResponse:
    entries = request.app.state.repository.get_audit_entries(limit)
    return AuditResponse(events=list(reversed(entries)))


@app.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    event_hub: EventHub = request.app.state.event_hub
    queue = event_hub.subscribe()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            event_hub.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/api/simulation/tick",
    response_model=SimulationTickResponse,
    dependencies=[Depends(verify_demo_token)],
)
def simulation_tick(request: Request) -> SimulationTickResponse:
    simulator: Simulator = request.app.state.simulator
    readings = simulator.tick()
    _publish_tick_events(request.app, readings)
    return SimulationTickResponse(
        tick=simulator.tick_count,
        readings=readings,
    )
