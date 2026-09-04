"""Errors raised by the read-only DuckDB/Parquet pricing-data access layer.

Kept structurally distinct from "no results" (spec Edge Cases / FR-018): a query that runs and
returns zero rows is not an error; a data source that cannot be reached or queried at all is.
The API layer (src/main.py) maps this to an HTTP 503, never a 200 with an empty body.
"""

from __future__ import annotations


class PricingDataUnavailableError(Exception):
    """Raised when the AWS pricing Parquet data cannot be read or queried."""
