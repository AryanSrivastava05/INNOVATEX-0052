import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
SYSTEM_PROMPT = (
    "You are writing a shift handoff for a SIMULATED patient monitoring demo. "
    "Use ONLY the facts in the JSON. Do not add diagnoses, treatment advice, or "
    "any numbers not present. Format as SBAR. End with: Decision support only, "
    "not a diagnosis."
)
ALERT_EXPLANATION_PROMPT = (
    "Rewrite the rule explanation for a SIMULATED patient monitoring demo in "
    "1-2 plain-language sentences. Use only the provided alert evidence, "
    "threshold, and rule explanation. Do not add diagnoses, treatment advice, "
    "or facts or numbers not present in the provided data."
)


def polish_handoff(handoff_json: dict[str, Any]) -> str | None:
    api_key = settings.groq_api_key
    if not api_key:
        logger.info("Groq handoff polishing skipped: API key is not configured")
        return None

    payload = {
        "model": settings.groq_model,
        "temperature": 0.2,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(handoff_json, separators=(",", ":")),
            },
        ],
    }
    try:
        with httpx.Client(timeout=settings.groq_timeout_seconds) as client:
            response = client.post(
                GROQ_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            logger.warning("Groq handoff polishing failed: empty response")
            return None
        return content.strip()
    except httpx.HTTPError:
        logger.warning("Groq handoff polishing failed: request error")
    except (KeyError, IndexError, TypeError, ValueError):
        logger.warning("Groq handoff polishing failed: invalid response")
    return None


def explain_alert(alert_json: dict[str, Any]) -> str | None:
    api_key = settings.groq_api_key
    if not api_key:
        logger.info("Groq alert explanation skipped: API key is not configured")
        return None

    payload = {
        "model": settings.groq_model,
        "temperature": 0.2,
        "max_tokens": 120,
        "messages": [
            {"role": "system", "content": ALERT_EXPLANATION_PROMPT},
            {
                "role": "user",
                "content": json.dumps(alert_json, separators=(",", ":")),
            },
        ],
    }
    try:
        with httpx.Client(timeout=settings.groq_timeout_seconds) as client:
            response = client.post(
                GROQ_CHAT_COMPLETIONS_URL,
                headers={"Authorization": "Bearer " + api_key},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            logger.warning("Groq alert explanation failed: empty response")
            return None
        return content.strip()
    except httpx.HTTPError:
        logger.warning("Groq alert explanation failed: request error")
    except (KeyError, IndexError, TypeError, ValueError):
        logger.warning("Groq alert explanation failed: invalid response")
    return None