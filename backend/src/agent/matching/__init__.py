"""Cross-provider matching for the agent's comparisons (024-agent-pricing-questions, research
R1–R7).

- `profiles`: what a catalog product is (function, category, specs, billing unit kind).
- `quality`: the fixed rules that label a match exact / close / partial / no equivalent.
- `usage`: the only usage conversions allowed (same kind of billing unit), and default usage.
- `regions`: nearest-region guesses from a reviewed location table.
- `book`: the per-message references (`S…`, `C…`) the model picks by.
- `candidates`: the batch candidate finder over the provider adapters.

agent-04's reviewed mappings will replace `candidates` as the source of matches; the rest stays.
"""
