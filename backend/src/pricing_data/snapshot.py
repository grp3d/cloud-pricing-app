"""Pricing snapshot layout shared by the pricing-data modules.

The Parquet tables (service_dim/, product_dim/, product_attribute/, region_dim/, price_fact/)
are each independently partitioned by `snapshot_date=YYYY-MM-DD`. Per research.md #2 and
Constitution Principle I, a single request must pin one snapshot date and use it consistently
across all five tables, so a price is never computed from a mix of two different days' data.

016-canvas-icon-layout (FR-014): which date that is is no longer worked out per call by scanning
for the newest folder — every lookup uses `active_snapshot.get_active_snapshot_date()`, which only
ever moves to a snapshot the upstream job has marked complete in all five tables.
"""

from __future__ import annotations

# The five pricing tables every snapshot date must exist in.
TABLES = ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact")
_TABLES = TABLES
