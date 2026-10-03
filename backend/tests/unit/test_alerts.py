"""Alerts to the environment's SNS topic (018-app-cloud-deployment, FR-044; research.md R10).

`notify` never raises: an alert that can't be sent is logged, so a failed alert never turns a
backup or health result into a crash (Story 7 AS3 — the failure is visible in the logs).
"""

from __future__ import annotations

import pytest

from src.ops import alerts


class _StubSNS:
    def __init__(self, fail: bool = False) -> None:
        self.published: list[dict] = []
        self.fail = fail

    def publish(self, **kwargs):
        if self.fail:
            raise RuntimeError("sns unavailable")
        self.published.append(kwargs)
        return {"MessageId": "1"}


@pytest.fixture
def topic(monkeypatch):
    monkeypatch.setattr(alerts.settings, "alert_topic_arn", "arn:aws:sns:us-east-1:0:t")
    monkeypatch.setattr(alerts.settings, "app_environment", "prod")


def test_publishes_to_the_topic_with_environment_in_subject(monkeypatch, topic):
    sns = _StubSNS()
    monkeypatch.setattr(alerts, "_client", lambda: sns)
    assert alerts.notify("backup failed", subject="Backup failed") is True
    assert sns.published == [
        {
            "TopicArn": "arn:aws:sns:us-east-1:0:t",
            "Subject": "[cloud-pricing-app prod] Backup failed",
            "Message": "backup failed",
        }
    ]


def test_unset_topic_only_logs(monkeypatch, log_output):
    monkeypatch.setattr(alerts.settings, "alert_topic_arn", None)
    monkeypatch.setattr(alerts, "_client", lambda: pytest.fail("no client without a topic"))
    assert alerts.notify("hello") is False
    assert [r["message"] for r in log_output()] == ["alert not sent: no topic"]


def test_publish_failure_is_logged_not_raised(monkeypatch, topic, log_output):
    monkeypatch.setattr(alerts, "_client", lambda: _StubSNS(fail=True))
    assert alerts.notify("hello") is False
    records = log_output()
    assert records[-1]["message"] == "alert not sent"
    assert records[-1]["level"] == "error"


def test_long_subjects_are_truncated_to_the_sns_limit(monkeypatch, topic):
    sns = _StubSNS()
    monkeypatch.setattr(alerts, "_client", lambda: sns)
    alerts.notify("x", subject="s" * 200)
    assert len(sns.published[0]["Subject"]) <= 100
