"""Test helpers for the agent (023): build a seeded standard architecture for a user."""

from __future__ import annotations

from pathlib import Path

from src.models.orm import Architecture, User
from src.models.schemas import ArchitectureExportFile
from src.services.architecture_transfer import build_architecture, specs_from_definition

SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "db" / "seed"
STANDARD_PRICING_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet_standard"


def seed_definition(provider: str, name: str):
    file = "standard_architectures.json" if provider == "aws" else (
        f"standard_architectures_{provider}.json")
    seed = ArchitectureExportFile.model_validate_json((SEED_DIR / file).read_text())
    return next(d for d in seed.architectures if d.name == name)


async def build_standard(db, owner: User, provider: str, name: str, *,
                         rename: str | None = None, public: bool = False) -> Architecture:
    """A copy of a seeded standard architecture owned by `owner` (committed)."""
    definition = seed_definition(provider, name)
    collections, connectors = specs_from_definition(definition)
    architecture = build_architecture(
        db, owner=owner, name=rename or definition.name, provider=definition.provider,
        collections=collections, connectors=connectors,
    )
    architecture.is_public = public
    await db.commit()
    return architecture


# 024: comparisons need every provider at once: AWS from the default fixture (which holds the
# AWS standard architectures' items) and Azure and GCP from the standard-architecture fixture.
# The snapshot loader refuses symlinks out of its root, so the three are copied once per run.
DEFAULT_PRICING_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"
_combined: Path | None = None


def combined_pricing_root() -> Path:
    global _combined
    if _combined is None:
        import atexit
        import shutil
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="pricing-combined-"))
        shutil.copytree(DEFAULT_PRICING_ROOT / "aws", root / "aws")
        for provider in ("azure", "gcp"):
            shutil.copytree(STANDARD_PRICING_ROOT / provider, root / provider)
        atexit.register(shutil.rmtree, root, True)
        _combined = root
    return _combined
