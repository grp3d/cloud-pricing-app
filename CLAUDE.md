# Cloud Pricing App

Start with [README.md](README.md). The development guide is [docs/development.md](docs/development.md);
current behaviour is described in [docs/features/](docs/features/).
The project's rules are in `.specify/memory/constitution.md`.

## Testing the agent with hosted models

Hosted-model runs (`pytest -m live_model` with an `anthropic:` model) are paid by the user. Follow
the budget rules in [docs/development.md](docs/development.md#the-agent): under $0.50 per
change unless the user agrees to more, ask first (cases, model, runs, cost), only the affected
cases, once, at most two runs per change, never repeat runs for stability, and stop on any API
error.

## Documentation

- The README is a fixed orientation page. Don't append feature notes to it; change it only when
  the repo's layout or the getting-started or deploy steps change.
- A feature or fix updates the matching page in `docs/features/` (or the other `docs/` pages it
  affects) and adds a line to `CHANGELOG.md` under the release it ships in.
- `specs/0NN-*/` are the per-feature design records. Don't rewrite them to match later changes.
- `docs/brief/` holds inputs (the original brief, change requests, the standard-architecture
  source). They aren't kept current, so don't describe current behaviour from them.
