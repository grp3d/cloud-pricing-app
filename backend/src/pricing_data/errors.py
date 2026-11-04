"""Errors raised by the read-only DuckDB/Parquet pricing-data access layer.

Kept structurally distinct from "no results" (spec Edge Cases / FR-018): a query that runs and
returns zero rows is not an error; a data source that cannot be reached or queried at all is.
The API layer (src/main.py) maps this to an HTTP 503, never a 200 with an empty body.
"""

from __future__ import annotations


class PricingDataUnavailableError(Exception):
    """Raised when a provider's pricing Parquet data cannot be read or queried. `provider`
    names whose data (019: the 503 says which provider is unavailable and why)."""

    def __init__(self, message: str = "", provider: str = "aws") -> None:
        super().__init__(message)
        self.provider = provider
