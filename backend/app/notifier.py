import logging

import httpx

from app.config import settings
from app.models import Alert

logger = logging.getLogger(__name__)


async def send_alert(alert: Alert) -> None:
    if not settings.webhook_url:
        return
    payload = {
        "patient_id": alert.patient_id,
        "severity": alert.severity,
        "metric": alert.metric,
        "observed": alert.observed,
        "threshold": alert.threshold,
        "explanation": alert.explanation,
        "ts": alert.updated_at.isoformat(),
        "simulated": True,
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(settings.webhook_url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Alert webhook delivery failed for alert %s", alert.id)
