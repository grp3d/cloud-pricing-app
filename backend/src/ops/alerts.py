"""Alerts to the environment's SNS topic (018-app-cloud-deployment, FR-038, FR-044;
research.md R10).

Used for backup failures, the uptime alert and the "up"/"status" address notice. With no
`ALERT_TOPIC_ARN` (a laptop), alerts are only logged. `notify` never raises: a failed alert is
logged, which is how it stays visible after teardown (Story 7 AS3).
"""

from __future__ import annotations

from src.config import settings
from src.logging_config import get_logger

logger = get_logger("cloud_pricing.ops.alerts")

# SNS rejects subjects longer than 100 characters.
_SUBJECT_LIMIT = 100


def _client():
    import boto3

    return boto3.client("sns")


def notify(message: str, subject: str | None = None) -> bool:
    """Publish `message`; return whether it was sent."""
    topic = settings.alert_topic_arn
    if not topic:
        logger.info("alert not sent: no topic", alert_subject=subject)
        return False
    full_subject = f"[cloud-pricing-app {settings.app_environment}] {subject or 'Notice'}"
    try:
        _client().publish(
            TopicArn=topic, Subject=full_subject[:_SUBJECT_LIMIT], Message=message
        )
    except Exception as exc:  # noqa: BLE001 — an alert failure must never stop the caller
        logger.error("alert not sent", alert_subject=subject, error=str(exc))
        return False
    logger.info("alert sent", alert_subject=subject)
    return True
