"""Product keys (026-agent-cross-cloud-translation, research R2).

A product key names a kind of product the same way in every region, so a cross-provider mapping
made once ("AWS t4g.xlarge → Azure D4s v5") holds wherever the user translates to. Each provider
builds it from its own attributes (Principle III):

| Provider | Key |
|---|---|
| AWS | service code + `usagetype` without the item's region prefix + `operation` |
| GCP | service id + display name without its location words |
| Azure | service + product + SKU + meter names (the region is a separate column) |

`find_by_key` finds the row with that key in another region: exactly one row, or `None` when the
product isn't sold there or several rows match (never a guess, Principle I).

The location words below are a reviewed list of the place names GCP puts in SKU names (checked
against the 2026-11-16 GCP snapshot). A name with a place not listed keeps it, so the product
only resolves in regions with the same name: a missed match, never a wrong one.
"""

from __future__ import annotations

import re

from src.pricing_data.providers.base import CatalogItem

SEP = "|"

# --- AWS -------------------------------------------------------------------------------------------

# The region prefixes AWS puts on usage types (us-east-1 has none; eu-west-1 is "EU").
_AWS_PREFIX = re.compile(
    r"^(?:EU|US[EW]\d|UG[EW]\d|EU[CNSW]\d|AP[ENS]\d|CA[NW]\d|SA[E]\d|ME[CS]\d|AF[S]\d|IL[C]\d"
    r"|MX[C]\d|EUS\d|APE\d|APN\d|APS\d|CPT|SAE\d|TWN\d|NZ[N]\d|AP[T]\d)-"
)


def aws_usage_type(usage_type: str) -> str:
    """`usagetype` without the item's own region prefix ("USW2-BoxUsage:t4g.xlarge" →
    "BoxUsage:t4g.xlarge"). Only the first prefix goes: the second region of a transfer stays."""
    return _AWS_PREFIX.sub("", usage_type, count=1)


def aws_key(item: CatalogItem) -> str:
    a = item.attributes
    return SEP.join(("aws", item.service_code, aws_usage_type(a.get("usagetype") or ""),
                     a.get("operation") or ""))


# --- GCP -------------------------------------------------------------------------------------------

_GCP_PLACES = (
    "Americas", "EMEA", "APAC", "Asia Pacific", "North America", "South America",
    "Central America", "Middle East", "Europe", "Asia", "Africa", "Australia", "US",
    "Northern Virginia", "Virginia", "South Carolina", "Oregon", "Iowa", "Los Angeles",
    "Las Vegas", "Salt Lake City", "Dallas", "Columbus", "Ohio", "Montreal", "Toronto",
    "Sao Paulo", "São Paulo", "Santiago", "Mexico", "Queretaro", "Querétaro", "Belgium",
    "London", "Frankfurt", "Netherlands", "Finland", "Zurich", "Milan", "Paris", "Madrid",
    "Warsaw", "Stockholm", "Turin", "Berlin", "Tel Aviv", "Israel", "Doha", "Dammam",
    "Johannesburg", "Japan", "Tokyo", "Osaka", "Seoul", "Korea", "Mumbai", "Delhi", "India",
    "Singapore", "Jakarta", "Indonesia", "Sydney", "Melbourne", "Hong Kong", "Taiwan",
    "Bangkok",
)
_PLACE = "(?:" + "|".join(re.escape(p) for p in sorted(_GCP_PLACES, key=len, reverse=True)) + ")"
_REGION_CODE = r"[a-z]+-[a-z]+\d+"
# One location: places joined by "/" ("Iowa/South Carolina/Oregon"), or a region code.
_LOCATION = rf"(?:{_PLACE}(?:/{_PLACE})*|{_REGION_CODE})"
_CODE_IN_PARENS = re.compile(rf"\s*\({_REGION_CODE}\)")
_TRAILING_IN_FOR = re.compile(rf"\s+(?:in|for)\s+{_LOCATION}$")
_TRAILING_PLACE = re.compile(rf"(?<!\bto)(?<!\bfrom)\s+{_LOCATION}(?:\s+Regional)?(?=$|\s+\()")
_INNER_PLACE = re.compile(rf"(?<=\s){_LOCATION}(?=\s|$)")


def gcp_name(display_name: str) -> str:
    """A GCP SKU name without its location words: trailing locations go, inner ones become
    `{L}` so "Dual-region" and "from X to Y" products stay distinct from regional ones."""
    name = _CODE_IN_PARENS.sub("", display_name).strip()
    name = _TRAILING_IN_FOR.sub("", name)
    name = _TRAILING_PLACE.sub("", name)
    name = _INNER_PLACE.sub("{L}", name)
    return re.sub(r"\s+", " ", name).strip()


def gcp_key(item: CatalogItem) -> str:
    return SEP.join(("gcp", item.service_code, gcp_name(item.summary)))


# --- Azure -----------------------------------------------------------------------------------------


def azure_key(item: CatalogItem) -> str:
    a = item.attributes
    return SEP.join(("azure", item.service_name or item.service_code, a.get("product_name", ""),
                     a.get("sku_name", ""), a.get("meter_name", "")))


# --- Lookup ----------------------------------------------------------------------------------------

_PAGE = 500
_MAX_PAGES = 10


def _narrowing(provider: str, key: str) -> dict:
    """Search filters that keep only rows that can have this key."""
    parts = key.split(SEP)
    if provider == "aws":
        return {"service_code": parts[1]}
    if provider == "gcp":
        words = [w for w in parts[2].split(" ") if w and "{" not in w][:3]
        return {"service_code": f"^{re.escape(parts[1])}$",
                **({"text": re.escape(" ".join(words))} if words else {})}
    return {"product_family": f"^{re.escape(parts[2])}$"}


MISSING, AMBIGUOUS = "missing", "ambiguous"


def resolve_key(adapter, snapshot, region: str, key: str, service_code: str | None = None,
                hint: str | None = None) -> tuple[CatalogItem | None, str | None]:
    """The one row of `region` with this product key, and why there is none: `MISSING` (not
    sold there) or `AMBIGUOUS` (several rows match and nothing stable tells them apart). When the
    same product is listed for the region itself and for a wider geography (Azure lists some
    meters under both "uksouth" and "europe"), the region's own row is the one. `hint` (a known
    item of the product) is kept for the callers' logs; it never picks among rows."""
    matches = list(_matches(adapter, snapshot, region, key, service_code).values())
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, MISSING
    own = [row for row in matches if row.attributes.get("location") == region]
    if len(own) == 1:
        return own[0], None
    return None, AMBIGUOUS


def find_by_key(adapter, snapshot, region: str, key: str, service_code: str | None = None
                ) -> CatalogItem | None:
    """The one row of `region` with this product key, or `None` (not sold there, or several
    rows match)."""
    return resolve_key(adapter, snapshot, region, key, service_code)[0]


def _matches(adapter, snapshot, region: str, key: str, service_code: str | None
             ) -> dict[str, CatalogItem]:
    filters = _narrowing(adapter.code, key)
    if service_code and adapter.code == "aws":
        filters["service_code"] = service_code
    matches: dict[str, CatalogItem] = {}
    offset = 0
    for _page in range(_MAX_PAGES):
        rows, total = adapter.search(snapshot, region=region, limit=_PAGE, offset=offset,
                                     **filters)
        for row in rows:
            if adapter.product_key(row) == key:
                matches[row.sku] = row
        offset += len(rows)
        if not rows or offset >= total:
            break
    return matches
