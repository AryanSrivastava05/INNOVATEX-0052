import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)


@pytest.fixture
def live_client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_synthetic_decision_support_status() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "simulated": True,
        "message": "Decision support only. Not a diagnosis.",
    }


def test_cors_allows_only_configured_frontend_origin() -> None:
    allowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    disallowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in disallowed.headers


def test_dashboard_contains_simulated_patients_and_vitals(live_client) -> None:
    response = live_client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["simulated"] is True
    assert len(payload["patients"]) == 12
    assert payload["patients"][0]["patient"]["id"] == "P001"
    assert payload["patients"][0]["simulated"] is True


def test_dashboard_is_sorted_by_score_then_oldest_unacknowledged_alert(
    live_client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    monkeypatch.setattr(settings, "tick_seconds", 60)
    live_client.post(
        "/api/scenarios/tachycardia?patient_id=P002",
        headers={"X-Demo-Token": "test-demo-token"},
    )

    patients = live_client.get("/api/dashboard").json()["patients"]

    assert [patient["score"] for patient in patients] == sorted(
        (patient["score"] for patient in patients),
        reverse=True,
    )
    assert patients[0]["patient"]["id"] == "P002"


def test_patient_profile_and_history_return_simulated_readings(live_client) -> None:
    profile = live_client.get("/api/patients/P001")
    history = live_client.get("/api/patients/P001/history?limit=5")

    assert profile.status_code == 200
    assert profile.json()["simulated"] is True
    assert profile.json()["patient"]["id"] == "P001"
    assert history.status_code == 200
    assert history.json()["simulated"] is True
    readings = history.json()["readings"]
    assert len(readings) == 5
    assert [reading["ts"] for reading in readings] == sorted(
        reading["ts"] for reading in readings
    )


def test_unknown_patient_returns_consistent_not_found_error(live_client) -> None:
    response = live_client.get("/api/patients/P999")

    assert response.status_code == 404
    assert set(response.json()) == {"error", "detail"}
    assert response.json()["error"] == "not_found"
    assert response.json()["detail"] == "Patient P999 not found"


def test_tick_requires_configured_demo_token(live_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")

    rejected = live_client.post("/api/simulation/tick")
    accepted = live_client.post(
        "/api/simulation/tick",
        headers={"X-Demo-Token": "test-demo-token"},
    )

    assert rejected.status_code == 401
    assert set(rejected.json()) == {"error", "detail"}
    assert rejected.json()["error"] == "unauthorized"
    assert accepted.status_code == 200
    assert accepted.json()["tick"] == 1
    assert accepted.json()["simulated"] is True
    assert len(accepted.json()["readings"]) == 12


def test_lifespan_runs_periodic_simulation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tick_seconds", 0.02)

    with TestClient(app):
        time.sleep(0.06)
        assert app.state.simulator.tick_count >= 1


def test_threshold_config_is_labeled_illustrative(live_client) -> None:
    response = live_client.get("/api/config/thresholds")

    assert response.status_code == 200
    payload = response.json()
    assert payload["demo_only"] is True
    assert "Illustrative" in payload["label"]
    assert payload["thresholds"]["spo2"] == {
        "warning_below": 92,
        "critical_below": 90,
    }


def test_alert_list_and_acknowledge_routes(live_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    live_client.post(
        "/api/simulation/tick",
        headers={"X-Demo-Token": "test-demo-token"},
    )

    listed = live_client.get("/api/alerts?status=active")
    assert listed.status_code == 200
    assert listed.json()["simulated"] is True
    alert = next(item for item in listed.json()["alerts"] if item["type"] == "heart_rate_high")

    acknowledged = live_client.post(
        f"/api/alerts/{alert['id']}/acknowledge",
        json={"note": "reviewed"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["simulated"] is True
    assert acknowledged.json()["alert"]["status"] == "acknowledged"
    assert acknowledged.json()["alert"]["ack_note"] == "reviewed"
    listed_acknowledged = live_client.get("/api/alerts?status=acknowledged")
    assert any(
        item["id"] == alert["id"]
        for item in listed_acknowledged.json()["alerts"]
    )


def test_acknowledging_unknown_alert_returns_not_found(live_client) -> None:
    response = live_client.post("/api/alerts/missing/acknowledge")

    assert response.status_code == 404
    assert response.json() == {
        "error": "not_found",
        "detail": "Alert missing not found",
    }


def test_dashboard_filter_and_patient_search(live_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    live_client.post(
        "/api/simulation/tick",
        headers={"X-Demo-Token": "test-demo-token"},
    )

    all_patients = live_client.get("/api/dashboard?filter=all")
    searched = live_client.get("/api/dashboard?q=p001")
    needs_review = live_client.get("/api/dashboard?filter=needs_review")

    assert len(all_patients.json()["patients"]) == 12
    all_statuses = all_patients.json()["patients"]
    scores = [item["score"] for item in all_statuses]
    assert scores == sorted(scores, reverse=True)
    assert [item["patient"]["id"] for item in searched.json()["patients"]] == ["P001"]
    assert needs_review.json()["patients"]
    assert all(
        item["active_alert_count"] > 0 for item in needs_review.json()["patients"]
    )

    active_alerts = live_client.get("/api/alerts?status=active").json()["alerts"]
    score_by_patient = {
        item["patient"]["id"]: item["score"] for item in all_statuses
    }
    alert_scores = [score_by_patient[item["patient_id"]] for item in active_alerts]
    assert alert_scores == sorted(alert_scores, reverse=True)
    alert = active_alerts[0]
    live_client.post(f"/api/alerts/{alert['id']}/acknowledge")
    acknowledged = live_client.get("/api/dashboard?filter=acknowledged")
    assert any(
        item["patient"]["id"] == alert["patient_id"]
        for item in acknowledged.json()["patients"]
    )


def test_scenario_trigger_moves_p002_to_dashboard_top_and_audits(
    live_client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    monkeypatch.setattr(settings, "tick_seconds", 60)

    scenario_list = live_client.get("/api/scenarios")
    assert scenario_list.status_code == 200
    assert scenario_list.json()["scenarios"] == [
        "spo2_decline",
        "tachycardia",
        "bp_spike",
        "sensor_dropout",
        "recovery",
    ]
    rejected = live_client.post(
        "/api/scenarios/tachycardia?patient_id=P002",
    )
    assert rejected.status_code == 401

    triggered = live_client.post(
        "/api/scenarios/tachycardia?patient_id=P002",
        headers={"X-Demo-Token": "test-demo-token"},
    )
    assert triggered.status_code == 200
    assert triggered.json()["simulated"] is True
    assert triggered.json()["latest"]["hr"] == 135

    dashboard = live_client.get("/api/dashboard").json()["patients"]
    assert dashboard[0]["patient"]["id"] == "P002"

    alert = next(
        item
        for item in live_client.get("/api/alerts?status=active").json()["alerts"]
        if item["patient_id"] == "P002"
    )
    live_client.post(f"/api/alerts/{alert['id']}/acknowledge")

    audit_response = live_client.get("/api/audit?limit=50")
    assert audit_response.status_code == 200
    assert audit_response.json()["simulated"] is True
    audit_types = [item["event"] for item in audit_response.json()["events"]]
    assert "scenario_triggered" in audit_types
    assert "tick" in audit_types
    assert "alert_create" in audit_types
    assert "alert_acknowledged" in audit_types


def test_invalid_scenario_and_patient_return_not_found(live_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    headers = {"X-Demo-Token": "test-demo-token"}

    invalid_scenario = live_client.post(
        "/api/scenarios/unknown?patient_id=P002",
        headers=headers,
    )
    invalid_patient = live_client.post(
        "/api/scenarios/tachycardia?patient_id=P999",
        headers=headers,
    )

    assert invalid_scenario.status_code == 404
    assert set(invalid_scenario.json()) == {"error", "detail"}
    assert invalid_patient.status_code == 404
    assert set(invalid_patient.json()) == {"error", "detail"}


def test_missing_data_produces_signal_lost_alert(live_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    monkeypatch.setattr(settings, "tick_seconds", 60)

    response = live_client.post(
        "/api/scenarios/sensor_dropout?patient_id=P002",
        headers={"X-Demo-Token": "test-demo-token"},
    )

    assert response.status_code == 200
    assert response.json()["latest"]["quality"] == "missing"
    alerts = live_client.get("/api/alerts?status=active").json()["alerts"]
    assert any(
        alert["patient_id"] == "P002" and alert["type"] == "signal_lost"
        for alert in alerts
    )


def test_bad_demo_token_returns_401_and_standard_error_shape(
    live_client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "demo_token", "expected-token")

    response = live_client.post(
        "/api/simulation/tick",
        headers={"X-Demo-Token": "wrong-token"},
    )

    assert response.status_code == 401
    assert set(response.json()) == {"error", "detail"}
    assert response.json()["error"] == "unauthorized"


def test_validation_errors_use_standard_error_shape(live_client) -> None:
    response = live_client.get("/api/patients/P001/history?limit=0")

    assert response.status_code == 422
    assert set(response.json()) == {"error", "detail"}


def test_handoff_route_accepts_window_and_returns_sbar_text(live_client) -> None:
    response = live_client.get("/api/handoff?window_minutes=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["simulated"] is True
    assert payload["generated_at"]
    assert all(
        key in payload
        for key in ("new_alerts", "worsening", "resolved", "unacknowledged")
    )
    assert "Situation:" in payload["text"]
    assert "Background:" in payload["text"]
    assert "Assessment:" in payload["text"]
    assert "Review needed:" in payload["text"]
    assert "Decision support only. Not a diagnosis." in payload["text"]


def test_handoff_rejects_invalid_window(live_client) -> None:
    response = live_client.get("/api/handoff?window_minutes=0")

    assert response.status_code == 422
