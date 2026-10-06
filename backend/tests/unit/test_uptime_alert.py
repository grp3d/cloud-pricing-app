"""The forgotten-instance alert (018-app-cloud-deployment, FR-044, Story 7, SC-012;
research.md R10). Alert only — nothing is ever torn down automatically.

Run every 30 minutes by a timer: past `UPTIME_ALERT_HOURS` of uptime it alerts, then again every
`UPTIME_ALERT_REPEAT_HOURS` while the instance stays up. A failed alert is logged, not raised,
and retried at the next run.
"""

from __future__ import annotations

import pytest

from src.ops import alerts, uptime

HOUR = 3600.0
NOW = 1_800_000_000.0


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setattr(uptime.settings, "uptime_alert_hours", 12)
    monkeypatch.setattr(uptime.settings, "uptime_alert_repeat_hours", 12)
    monkeypatch.setattr(uptime.settings, "app_environment", "prod")
    sent: list[str] = []
    monkeypatch.setattr(
        alerts, "notify", lambda message, subject=None: sent.append(message) or True
    )
    proc = tmp_path / "uptime"
    state = tmp_path / "state" / "last-uptime-alert"

    def run(hours_up: float, now: float = NOW) -> dict:
        proc.write_text(f"{hours_up * HOUR:.2f} 12345.67\n")
        return uptime.run_uptime_alert(uptime_path=proc, state_path=state, now=lambda: now)

    return run, sent, state


def test_below_the_threshold_nothing_is_sent(host):
    run, sent, state = host
    result = run(11.9)
    assert result == {"alerted": False, "uptime_hours": 11.9}
    assert sent == []
    assert not state.exists()


def test_first_crossing_alerts_and_records_the_time(host):
    run, sent, state = host
    result = run(12.1)
    assert result["alerted"] is True
    assert len(sent) == 1
    assert "prod" in sent[0] and "12.1 hours" in sent[0]
    assert float(state.read_text()) == NOW


def test_within_the_repeat_interval_nothing_more_is_sent(host):
    run, sent, _ = host
    run(12.1)
    assert run(23.5, now=NOW + 11.4 * HOUR)["alerted"] is False
    assert len(sent) == 1


def test_after_the_repeat_interval_it_alerts_again(host):
    run, sent, _ = host
    run(12.1)
    assert run(24.2, now=NOW + 12.1 * HOUR)["alerted"] is True
    assert len(sent) == 2


def test_a_reboot_clears_the_record(host):
    run, sent, state = host
    run(12.1)
    run(0.5, now=NOW + HOUR)
    assert not state.exists()
    assert run(12.2, now=NOW + 13 * HOUR)["alerted"] is True
    assert len(sent) == 2


def test_a_failed_alert_is_logged_not_raised_and_retried(host, monkeypatch, log_output):
    run, _, state = host
    monkeypatch.setattr(alerts, "notify", lambda message, subject=None: False)
    result = run(12.5)
    assert result["alerted"] is False
    assert not state.exists()  # tried again at the next run
    assert any(r["message"] == "uptime alert not sent" for r in log_output())


def test_never_tears_anything_down():
    import inspect

    source = inspect.getsource(uptime)
    assert "destroy" not in source and "terminate" not in source.lower()
