"""FastAPI application entrypoint.

Registers routers (added incrementally per user story) and maps pricing-data-source outages
to a distinct HTTP 503 (spec FR-018) — never conflated with an empty/`200` "no results"
response, and never surfaced as an unhandled 500.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.pricing_data.active_snapshot import run_check
from src.pricing_data.catalog import EmptyCatalogFilterError, InvalidRegexPatternError
from src.pricing_data.errors import PricingDataUnavailableError
from src.services.architecture_transfer import InvalidImportFileError
from src.services.price_calculation import EmptySnapshotError

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("cloud_pricing")

async def _snapshot_monitor() -> None:
    """016-canvas-icon-layout, FR-015/FR-023: re-check the pricing data every
    `SNAPSHOT_CHECK_INTERVAL_SECONDS`. Sequential, so a slow check delays the next rather than
    overlapping it; one failed check never stops the loop."""
    while True:
        await asyncio.sleep(settings.snapshot_check_interval_seconds)
        try:
            await asyncio.to_thread(run_check)
        except Exception:  # noqa: BLE001
            logger.exception("pricing snapshot check failed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # FR-017: settle the active snapshot before serving any pricing request. A pinned
    # ACTIVE_SNAPSHOT_DATE missing from a table raises here, so the server refuses to start.
    await asyncio.to_thread(run_check, at_startup=True)
    monitor = asyncio.create_task(_snapshot_monitor())
    try:
        yield
    finally:
        monitor.cancel()
        try:
            await monitor
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Cloud Pricing API", version="0.1.0", root_path_in_servers=False, lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PricingDataUnavailableError)
async def pricing_data_unavailable_handler(
    request: Request, exc: PricingDataUnavailableError
) -> JSONResponse:
    logger.error("pricing data source unavailable: %s (%s)", exc, request.url)
    return JSONResponse(
        status_code=503,
        content={
            "error": "pricing_data_unavailable",
            "message": "The AWS pricing data source is temporarily unreachable. Please retry.",
        },
    )


@app.exception_handler(EmptyCatalogFilterError)
async def empty_catalog_filter_handler(
    request: Request, exc: EmptyCatalogFilterError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": "empty_filter", "message": str(exc)})


@app.exception_handler(InvalidRegexPatternError)
async def invalid_regex_pattern_handler(
    request: Request, exc: InvalidRegexPatternError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_regex_pattern", "message": str(exc), "field": exc.field},
    )


@app.exception_handler(EmptySnapshotError)
async def empty_snapshot_handler(request: Request, exc: EmptySnapshotError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": "empty_snapshot", "message": str(exc)})


@app.exception_handler(InvalidImportFileError)
async def invalid_import_file_handler(
    request: Request, exc: InvalidImportFileError
) -> JSONResponse:
    # 014-architecture-templates-import-export, spec FR-019: the file as a whole isn't an
    # architecture export — nothing was imported.
    return JSONResponse(
        status_code=400, content={"error": "invalid_import_file", "message": str(exc)}
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Routers are registered here as each user story's endpoints are implemented.
from src.api.admin_system import router as admin_system_router  # noqa: E402
from src.api.admin_users import router as admin_users_router  # noqa: E402
from src.api.architectures import router as architectures_router  # noqa: E402
from src.api.auth import router as auth_router  # noqa: E402
from src.api.calculate import router as calculate_router  # noqa: E402
from src.api.catalog import router as catalog_router  # noqa: E402
from src.api.collections import router as collections_router  # noqa: E402
from src.api.connectors import router as connectors_router  # noqa: E402
from src.api.providers import router as providers_router  # noqa: E402
from src.api.regions import router as regions_router  # noqa: E402
from src.api.sku_selections import router as sku_selections_router  # noqa: E402

app.include_router(providers_router, prefix="/api/v1")
app.include_router(regions_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(architectures_router, prefix="/api/v1")
app.include_router(collections_router, prefix="/api/v1")
app.include_router(sku_selections_router, prefix="/api/v1")
app.include_router(calculate_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_users_router, prefix="/api/v1")
app.include_router(admin_system_router, prefix="/api/v1")
app.include_router(connectors_router, prefix="/api/v1")
