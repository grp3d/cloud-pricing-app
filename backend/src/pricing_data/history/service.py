"""Keeping each provider's price history up to date (019, research R10, T075).

`update_history(provider)` brings the provider's history in line with every snapshot in the
source: on first start it is the backfill (oldest to newest, one snapshot at a time), and after
an active snapshot switches it adds the new week. It runs in a background thread, one build per
provider at a time; its progress and last error are in `state.json` for the Admin tab and the
Trends `building` status. A failure is recorded and never affects pricing.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from src.config import settings
from src.logging_config import get_logger
from src.pricing_data.history.builder import build_history, select_weeks
from src.pricing_data.history.source import list_manifests, snapshot_opener
from src.pricing_data.history.store import HistoryStore
from src.pricing_data.providers.registry import get_provider, has_adapter
from src.pricing_data.snapshot import PROVIDERS
from src.pricing_data.storage import Store, open_store

logger = get_logger("cloud_pricing.history")

_locks = {provider: threading.Lock() for provider in PROVIDERS}


def history_store(provider: str) -> HistoryStore:
    return HistoryStore(Path(settings.pricing_history_dir), provider)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def update_history(provider: str, *, source: Store | None = None) -> bool:
    """Build what is missing. Returns False (doing nothing) when a build is already running
    for this provider."""
    if not has_adapter(provider):
        return False
    lock = _locks[provider]
    if not lock.acquire(blocking=False):
        return False
    store = history_store(provider)
    try:
        store.update_state(backfill="running", started_at=_now())
        source = source or open_store(settings)
        adapter = get_provider(provider)
        weeks = select_weeks(list_manifests(source, provider))

        def progress(done: int, total: int) -> None:
            logger.debug("price history progress", provider=provider, done=done, total=total)

        build_history(store, weeks, adapter.write_comparable_prices,
                      snapshot_opener(source, adapter.comparable_tables), on_progress=progress)
        store.update_state(backfill="done", last_error=None, finished_at=_now())
        return True
    except Exception as exc:  # noqa: BLE001 — recorded for the Admin tab; pricing is unaffected
        logger.exception("price history build failed", provider=provider)
        store.update_state(backfill="failed", last_error=str(exc), finished_at=_now())
        return True
    finally:
        lock.release()


def is_building(provider: str) -> bool:
    return _locks[provider].locked()


def update_all_in_background(providers: list[str] | None = None) -> threading.Thread:
    """Run `update_history` for each provider in turn, in one daemon thread."""

    def run() -> None:
        for provider in providers or list(PROVIDERS):
            update_history(provider)

    thread = threading.Thread(target=run, name="price-history", daemon=True)
    thread.start()
    return thread
