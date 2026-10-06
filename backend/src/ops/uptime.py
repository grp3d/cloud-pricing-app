"""`ops uptime-alert` — the forgotten-instance alert (018-app-cloud-deployment, FR-044, Story 7,
SC-012; research.md R10).

A systemd timer runs this every 30 minutes on the instance. Once host uptime passes
`UPTIME_ALERT_HOURS` it publishes an alert, then repeats every `UPTIME_ALERT_REPEAT_HOURS` while
the instance stays up. It only ever alerts: the instance is never stopped by it (clarification).
The time of the last alert is kept in a small state file; a failed alert is logged and retried
at the next run.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from src.config import settings
from src.logging_config import get_logger
from src.ops import alerts

logger = get_logger("cloud_pricing.ops.uptime")

# The host's /proc/uptime, mounted read-only into the ops container (compose.yaml).
HOST_UPTIME = Path("/host/proc/uptime")
STATE_FILE = Path("/var/lib/app/last-uptime-alert")


def run_uptime_alert(
    *,
    uptime_path: Path = HOST_UPTIME,
    state_path: Path = STATE_FILE,
    now: Callable[[], float] = time.time,
) -> dict:
    uptime_hours = round(float(uptime_path.read_text().split()[0]) / 3600, 1)
    threshold = settings.uptime_alert_hours
    if uptime_hours < threshold:
        state_path.unlink(missing_ok=True)  # a reboot, or not yet: start over
        return {"alerted": False, "uptime_hours": uptime_hours}

    current = now()
    try:
        last = float(state_path.read_text())
    except (OSError, ValueError):
        last = None
    if last is not None and current - last < settings.uptime_alert_repeat_hours * 3600:
        return {"alerted": False, "uptime_hours": uptime_hours}

    message = (
        f"{settings.app_environment} has been up for {uptime_hours} hours (alert threshold "
        f"{threshold} h). If it is no longer needed, run: deploy/app down --env "
        f"{settings.app_environment} (or the app workflow's down action)."
    )
    if not alerts.notify(message, subject=f"Still running after {uptime_hours} h"):
        logger.error("uptime alert not sent", uptime_hours=uptime_hours)
        return {"alerted": False, "uptime_hours": uptime_hours}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(str(current))
    logger.info("uptime alert sent", uptime_hours=uptime_hours)
    return {"alerted": True, "uptime_hours": uptime_hours}
