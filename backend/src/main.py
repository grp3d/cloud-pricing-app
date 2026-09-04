"""FastAPI application entrypoint.

Registers routers (added incrementally per user story) and maps pricing-data-source outages
to a distinct HTTP 503 (spec FR-018) — never conflated with an empty/`200` "no results"
response, and never surfaced as an unhandled 500.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.pricing_data.catalog import EmptyCatalogFilterError
from src.pricing_data.errors import PricingDataUnavailableError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloud_pricing")

app = FastAPI(title="Cloud Pricing API", version="0.1.0", root_path_in_servers=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Routers are registered here as each user story's endpoints are implemented.
from src.api.architectures import router as architectures_router  # noqa: E402
from src.api.calculate import router as calculate_router  # noqa: E402
from src.api.catalog import router as catalog_router  # noqa: E402
from src.api.collections import router as collections_router  # noqa: E402
from src.api.connectors import router as connectors_router  # noqa: E402
from src.api.providers import router as providers_router  # noqa: E402
from src.api.sku_selections import router as sku_selections_router  # noqa: E402

app.include_router(providers_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(architectures_router, prefix="/api/v1")
app.include_router(collections_router, prefix="/api/v1")
app.include_router(sku_selections_router, prefix="/api/v1")
app.include_router(calculate_router, prefix="/api/v1")
app.include_router(connectors_router, prefix="/api/v1")
