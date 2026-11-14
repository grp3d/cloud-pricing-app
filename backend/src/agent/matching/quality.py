"""Match quality (024, clarification 3, FR-009b, research R3).

The app sets the highest label a match may carry, from the two products' profiles:

| Label | Rule |
|---|---|
| exact | same function, same billing unit kind, every spec the source has is equal |
| close | as exact, but only minor differences: memory larger by up to 2×, a different processor architecture, burstable or steady CPU, high availability or redundancy, or a spec this product doesn't publish |
| partial | same category, but a different function, billing unit, or a major spec difference (vCPU, less memory or over 2×, machine type, operating system, engine, storage access tier, kind of data transfer, DNS zone type, load balancer type) |
| no equivalent | no product in the same category |

`differences` are short app-written facts, "this product vs the original". The agent may lower a
label (with a reason), never raise it (`lower`).
"""

from __future__ import annotations

from decimal import Decimal

from src.agent.matching.profiles import FUNCTION_LABELS, ProductProfile

LABELS = ("exact", "close", "partial", "no_equivalent")
_RANK = {label: rank for rank, label in enumerate(LABELS)}

_SPEC_NAMES = {
    "memory_gib": "memory",
    "vcpu": "vCPU count",
    "arch": "processor architecture",
    "os": "operating system",
    "engine": "engine",
    "ha": "high availability",
    "storage_class": "access tier",
    "redundancy": "redundancy",
    "purpose": "machine type",
    "burstable": "burstable CPU",
    "transfer": "kind of transfer",
    "visibility": "DNS zone type",
    "lb_layer": "load balancer type",
}


def _fmt(value: object) -> str:
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    return str(value)


def _spec_difference(key: str, source: object, target: object) -> tuple[str, bool]:
    """(the difference, whether it is major)."""
    if key == "vcpu":
        return f"{target} vCPU vs {source} vCPU", True
    if key == "memory_gib":
        ratio = Decimal(str(target)) / Decimal(str(source)) if source else Decimal(0)
        major = ratio < 1 or ratio > 2
        return f"memory {_fmt(target)} GiB vs {_fmt(source)} GiB", major
    if key in ("arch", "os"):
        return f"{target} vs {source}", key == "os"
    if key == "engine":
        return f"engine {target} vs {source}", True
    if key == "ha":
        def word(v):
            return "high availability" if v else "single zone"
        return f"{word(target)} vs {word(source)}", False
    if key == "storage_class":
        return f"access tier {target} vs {source}", True
    if key == "redundancy":
        return f"redundancy {target} vs {source}", False
    if key == "purpose":
        return f"{target} machine vs {source}", True
    if key == "burstable":
        def word(v):
            return "burstable CPU" if v else "steady CPU"
        return f"{word(target)} vs {word(source)}", False
    if key == "transfer":
        return f"{str(target).replace('_', '-')} transfer vs {str(source).replace('_', '-')}", True
    if key == "visibility":
        return f"{target} DNS vs {source}", True
    if key == "lb_layer":
        return f"{target} load balancer vs {source}", True
    return f"{_SPEC_NAMES.get(key, key)} {target} vs {source}", False


def quality(source: ProductProfile,
            target: ProductProfile | None) -> tuple[str, list[str]]:
    """The highest label this match may carry, and the differences found."""
    if target is None or (source.category and target.category
                          and source.category != target.category):
        return "no_equivalent", ["no product in the same category"]
    if target.function != source.function:
        return "partial", [
            f"{FUNCTION_LABELS.get(target.function, target.function)}, not "
            f"{FUNCTION_LABELS.get(source.function, source.function)}"]
    if target.unit_kind != source.unit_kind or "unknown" in (source.unit_kind, target.unit_kind):
        return "partial", [
            f"billed per {target.unit_kind.replace('_', ' ')}, not per "
            f"{source.unit_kind.replace('_', ' ')}; usage can't be converted"]
    differences: list[str] = []
    major = False
    for key, value in source.specs.items():
        if key not in _SPEC_NAMES:
            continue
        if key not in target.specs:
            differences.append(f"{_SPEC_NAMES[key]} not published for this product")
            continue
        other = target.specs[key]
        if other == value:
            continue
        text, is_major = _spec_difference(key, value, other)
        differences.append(text)
        major = major or is_major
    if major:
        return "partial", differences
    return ("close" if differences else "exact"), differences


def lower(app_label: str, shown: str | None, reason: str | None) -> str:
    """The label shown: the app's, or a lower one the agent chose with a stated reason."""
    if shown is None or shown == app_label:
        return app_label
    if shown not in _RANK:
        from src.agent.operations import ToolError

        raise ToolError(f"unknown match quality {shown!r}")
    if _RANK[shown] < _RANK[app_label]:
        from src.agent.operations import ToolError

        raise ToolError(
            f"A match quality can't be higher than the app's ({app_label}); you sent {shown}.")
    if not (reason and reason.strip()):
        from src.agent.operations import ToolError

        raise ToolError("Give a reason when you lower a match quality.")
    return shown
