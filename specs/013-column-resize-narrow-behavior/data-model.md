# Data Model: Architecture Panel Narrow-Width Layout

No new or changed data entities. This feature is a presentation-layer layout change to the
existing `ProviderArchitecturePanel` component — it reads the same `ArchitectureSummary[]`
and other props already defined in `ProviderArchitecturePanelProps`
(`frontend/src/components/workspace/ProviderArchitecturePanel.tsx`) and writes no new
state. No Postgres schema, DuckDB query, or API contract is affected.
