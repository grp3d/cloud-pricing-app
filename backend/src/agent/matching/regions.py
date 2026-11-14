"""Regions for comparisons (024, research R6, FR-007).

A region the user names is used as given. Otherwise the app guesses the nearest region on the
other provider, from `region_locations.json` (a reviewed table: metro area, country, geography
and approximate coordinates): the same metro area first, then the nearest region in the same
geography, among the regions that have pricing data. A guess is always flagged `guessed`, so the
agent states it; there is no curated region equivalence.
"""

from __future__ import annotations

import difflib
import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

_TABLE = Path(__file__).with_name("region_locations.json")


@cache
def locations() -> dict[str, dict[str, dict]]:
    data = json.loads(_TABLE.read_text())
    return {provider: regions for provider, regions in data.items() if not provider.startswith("_")}


def known(provider: str, region: str) -> bool:
    return region in locations().get(provider, {})


def _distance(a: dict, b: dict) -> float:
    """Great-circle distance in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def region_guess(source_provider: str, source_region: str, target_provider: str,
                 available: set[str] | list[str]) -> str | None:
    """The nearest `target_provider` region with pricing data, or None (the agent then asks)."""
    source = locations().get(source_provider, {}).get(source_region)
    if source is None:
        return None
    if source_provider == target_provider and source_region in available:
        return source_region
    targets = locations().get(target_provider, {})
    options = [(code, targets[code]) for code in sorted(available)
               if code in targets and targets[code]["geography"] == source["geography"]]
    if not options:
        return None
    same_metro = [code for code, loc in options
                  if loc["city"] == source["city"] and loc["country"] == source["country"]]
    if same_metro:
        return same_metro[0]
    return min(options, key=lambda option: (_distance(source, option[1]), option[0]))[0]


@dataclass(frozen=True)
class RegionChoice:
    provider: str
    region: str | None
    guessed: bool
    available: bool
    reason: str | None = None


def resolve_region(provider: str, requested: str | None, *, available: set[str] | list[str],
                   near: tuple[str, str] | None = None) -> RegionChoice:
    """The region to price `provider` in. Raises `ToolError` for a name that isn't one of the
    provider's regions; a real region without pricing data is returned as not available, so the
    comparison shows that provider as unavailable rather than failing (US4)."""
    from src.agent.operations import ToolError

    available = set(available)
    if requested:
        if requested in available:
            return RegionChoice(provider, requested, False, True)
        if known(provider, requested):
            return RegionChoice(provider, requested, False, False,
                                f"no {provider.upper()} pricing data for {requested}")
        pool = sorted(available | set(locations().get(provider, {})))
        close = difflib.get_close_matches(requested, pool, n=4, cutoff=0.5)
        hint = f" Closest names: {', '.join(close)}." if close else ""
        raise ToolError(f"{requested} isn't a {provider.upper()} region.{hint} Regions with "
                        f"pricing data: {', '.join(sorted(available)) or 'none'}.")
    if near is not None:
        guess = region_guess(near[0], near[1], provider, available)
        if guess is not None:
            return RegionChoice(provider, guess, True, True)
        return RegionChoice(provider, None, True, False,
                            f"no {provider.upper()} region with pricing data near {near[1]}; "
                            "ask the user which region to use")
    raise ToolError(f"Name a region for {provider.upper()}. Regions with pricing data: "
                    f"{', '.join(sorted(available)) or 'none'}.")
