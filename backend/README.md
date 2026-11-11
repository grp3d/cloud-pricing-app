# Cloud Pricing Backend

FastAPI API, DuckDB queries over the pricing Parquet, Postgres for user data, and the `ops`
commands the deployment runs (`python -m src.ops`).

```bash
uv sync --extra dev && source .venv/bin/activate
alembic upgrade head
uvicorn src.main:app --reload --port 8000     # needs PRICING_DATA_URI in .env
uv run pytest                                 # needs cloud_pricing_test; see the guide
uv run ruff check src/ tests/
```

Setup, tests, the pricing fixture and the standard-architecture seed:
[docs/development.md](../docs/development.md). Settings:
[docs/configuration.md](../docs/configuration.md).
