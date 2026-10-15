from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.llm import (
    ALERT_EXPLANATION_PROMPT,
    GROQ_CHAT_COMPLETIONS_URL,
    SYSTEM_PROMPT,
    explain_alert,
    polish_handoff,
)
from app.main import app


HANDOFF_JSON = {
    "simulated": True,
    "new_alerts": [],
    "worsening": [],
    "resolved": [],
    "unacknowledged": [],
}


@pytest.fixture
def live_client():
    with TestClient(app) as test_client:
        yield test_client


def test_polish_handoff_success_posts_groq_chat_request(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "test-secret-key")
    monkeypatch.setattr(settings, "groq_model", "test-model")
    monkeypatch.setattr(settings, "groq_timeout_seconds", 4.5)
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": "SBAR output.\nDecision support only, not a diagnosis."}}]
    }
    response.raise_for_status = Mock()
    client = Mock()
    client.post.return_value = response

    class ClientContext:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 4.5

        def __enter__(self):
            return client

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.llm.httpx.Client", ClientContext)

    result = polish_handoff(HANDOFF_JSON)

    assert result == "SBAR output.\nDecision support only, not a diagnosis."
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    assert args == (GROQ_CHAT_COMPLETIONS_URL,)
    assert kwargs["headers"] == {"Authorization": "Bearer test-secret-key"}
    assert kwargs["json"]["model"] == "test-model"
    assert kwargs["json"]["temperature"] == 0.2
    assert kwargs["json"]["max_tokens"] == 400
    assert kwargs["json"]["messages"][0]["content"] == SYSTEM_PROMPT
    assert kwargs["json"]["messages"][1]["content"] == (
        '{"simulated":true,"new_alerts":[],"worsening":[],"resolved":[],'
        '"unacknowledged":[]}'
    )


def test_polish_handoff_skips_request_when_key_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "")

    def unexpected_request(*_args, **_kwargs):
        raise AssertionError("Groq must not be called without an API key")

    monkeypatch.setattr("app.llm.httpx.Client", unexpected_request)

    assert polish_handoff(HANDOFF_JSON) is None


def test_polish_handoff_returns_none_on_timeout_without_logging_key(
    monkeypatch,
    caplog,
) -> None:
    secret = "timeout-secret"
    monkeypatch.setattr(settings, "groq_api_key", secret)

    class ClientContext:
        def __init__(self, *, timeout: float) -> None:
            pass

        def __enter__(self):
            raise httpx.TimeoutException("request timed out")

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.llm.httpx.Client", ClientContext)

    assert polish_handoff(HANDOFF_JSON) is None
    assert secret not in caplog.text


def test_polish_handoff_returns_none_on_http_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "test-secret-key")

    class ClientContext:
        def __init__(self, *, timeout: float) -> None:
            pass

        def __enter__(self):
            client = Mock()
            client.post.side_effect = httpx.ConnectError("connection failed")
            return client

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.llm.httpx.Client", ClientContext)

    assert polish_handoff(HANDOFF_JSON) is None


def test_explain_alert_posts_only_alert_evidence_threshold_and_rule(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "alert-secret-key")
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": "Oxygen has fallen below the alert limit."}}]
    }
    response.raise_for_status = Mock()
    client = Mock()
    client.post.return_value = response

    class ClientContext:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == settings.groq_timeout_seconds

        def __enter__(self):
            return client

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.llm.httpx.Client", ClientContext)
    alert_json = {
        "evidence": [{"patient_id": "P001", "spo2": 89}],
        "threshold": 90,
        "rule_explanation": "SpO2 is below the critical threshold.",
    }

    assert explain_alert(alert_json) == "Oxygen has fallen below the alert limit."
    _, kwargs = client.post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer alert-secret-key"}
    assert kwargs["json"]["messages"][0]["content"] == ALERT_EXPLANATION_PROMPT
    assert kwargs["json"]["messages"][1]["content"] == (
        '{"evidence":[{"patient_id":"P001","spo2":89}],"threshold":90,'
        '"rule_explanation":"SpO2 is below the critical threshold."}'
    )


def test_explain_alert_returns_none_without_key_or_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert explain_alert({}) is None
    monkeypatch.setattr(settings, "groq_api_key", "alert-secret-key")

    class ClientContext:
        def __init__(self, *, timeout: float) -> None:
            pass

        def __enter__(self):
            raise httpx.TimeoutException("request timed out")

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.llm.httpx.Client", ClientContext)
    assert explain_alert({}) is None


def test_handoff_ai_failure_preserves_template(monkeypatch, live_client) -> None:
    def fail_polishing(_handoff_json) -> None:
        return None

    monkeypatch.setattr("app.llm.polish_handoff", fail_polishing)

    template = live_client.get("/api/handoff")
    with_ai = live_client.get("/api/handoff?ai=true")

    assert template.status_code == 200
    assert with_ai.status_code == 200
    assert with_ai.json()["text"] == template.json()["text"]
    assert with_ai.json()["ai_text"] is None
    assert with_ai.json()["ai_used"] is False


def test_alert_explanation_is_opt_in_cached_and_keeps_rule_text(
    monkeypatch,
    live_client,
) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    live_client.post(
        "/api/scenarios/tachycardia?patient_id=P002",
        headers={"X-Demo-Token": "test-demo-token"},
    )
    alert = next(
        item
        for item in live_client.get("/api/alerts").json()["alerts"]
        if item["patient_id"] == "P002"
    )
    calls: list[dict] = []

    def explain(alert_json: dict) -> str:
        calls.append(alert_json)
        return "The heart rate is above its configured demo limit."

    monkeypatch.setattr("app.llm.explain_alert", explain)
    live_client.post(
        "/api/simulation/tick",
        headers={"X-Demo-Token": "test-demo-token"},
    )
    assert calls == []

    ordinary = live_client.get(f"/api/alerts/{alert['id']}")
    assert ordinary.status_code == 200
    assert ordinary.json()["alert"]["ai_explanation"] is None
    assert calls == []

    generated = live_client.get(f"/api/alerts/{alert['id']}?ai=true")
    again = live_client.get(f"/api/alerts/{alert['id']}?ai=true")
    expected = "The heart rate is above its configured demo limit."
    assert generated.json()["alert"]["ai_explanation"] == expected
    assert generated.json()["alert"]["explanation"] == alert["explanation"]
    assert again.json()["alert"]["ai_explanation"] == expected
    assert len(calls) == 1
    assert set(calls[0]) == {"evidence", "threshold", "rule_explanation"}
    assert calls[0]["rule_explanation"] == alert["explanation"]


def test_alert_explanation_failure_preserves_rule_explanation(
    monkeypatch,
    live_client,
) -> None:
    monkeypatch.setattr(settings, "demo_token", "test-demo-token")
    live_client.post(
        "/api/scenarios/tachycardia?patient_id=P002",
        headers={"X-Demo-Token": "test-demo-token"},
    )
    alert = next(
        item
        for item in live_client.get("/api/alerts").json()["alerts"]
        if item["patient_id"] == "P002"
    )

    def fail_explaining(_alert_json: dict) -> None:
        return None

    monkeypatch.setattr("app.llm.explain_alert", fail_explaining)
    response = live_client.get(f"/api/alerts/{alert['id']}?ai=true")

    assert response.status_code == 200
    assert response.json()["alert"]["explanation"] == alert["explanation"]
    assert response.json()["alert"]["ai_explanation"] is None
