"""Service categories for Trends (019, research R9, data-model §2, FR-015a, FR-017).

Trend data stores each item's **service key**, never its category, so a rule change applies at
the next query with no rebuild. A service key is two grouping values joined by `|`:

| Provider | Key | Rule fields |
|---|---|---|
| AWS | `service_code|product_family` | `service_code`, `product_family` |
| Azure | `service_family|service_name` | `service_family`, `service_name` |
| GCP | `taxonomy_1|taxonomy_2` (levels after `GCP`) | `taxonomy_1`, `taxonomy_2` |

The matching rule with the highest priority wins; no match is uncategorized (None), which shows
only under "all categories".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import ServiceCategoryRule

CATEGORIES = ("compute", "storage", "database", "networking")
ALL = "all"

# The two fields a provider's service key holds, in order.
KEY_FIELDS: dict[str, tuple[str, str]] = {
    "aws": ("service_code", "product_family"),
    "azure": ("service_family", "service_name"),
    "gcp": ("taxonomy_1", "taxonomy_2"),
}


def service_key(first: str | None, second: str | None) -> str:
    return f"{first or ''}|{second or ''}"


def key_fields(provider: str, key: str) -> dict[str, str]:
    first, _sep, second = key.partition("|")
    names = KEY_FIELDS[provider]
    return {names[0]: first, names[1]: second}


@dataclass(frozen=True)
class Rule:
    provider: str
    match_field: str
    match_value: str
    category: str
    priority: int


class Categorizer:
    """Maps one provider's service keys to categories with a fixed rule set."""

    def __init__(self, rules: Iterable[Rule]) -> None:
        self._rules: dict[str, dict[tuple[str, str], Rule]] = {}
        for rule in rules:
            self._rules.setdefault(rule.provider, {})[(rule.match_field, rule.match_value)] = rule
        self._cache: dict[tuple[str, str], str | None] = {}

    def category_of(self, provider: str, key: str) -> str | None:
        cached = self._cache.get((provider, key), ...)
        if cached is not ...:
            return cached
        rules = self._rules.get(provider, {})
        best: Rule | None = None
        for field, value in key_fields(provider, key).items():
            rule = rules.get((field, value))
            if rule is not None and (best is None or rule.priority > best.priority):
                best = rule
        category = best.category if best else None
        self._cache[(provider, key)] = category
        return category

    def keys_for(self, provider: str, category: str, keys: Iterable[str]) -> set[str]:
        """The keys among `keys` in `category`; every key for "all"."""
        if category == ALL:
            return set(keys)
        return {k for k in keys if self.category_of(provider, k) == category}


async def load_categorizer(session: AsyncSession) -> Categorizer:
    rows = (await session.execute(select(ServiceCategoryRule))).scalars()
    return Categorizer(
        Rule(r.provider, r.match_field, r.match_value, r.category, r.priority) for r in rows
    )
