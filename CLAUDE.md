# Cloud Pricing App

Start with [README.md](README.md). The development guide is [docs/development.md](docs/development.md);
current behaviour is described in [docs/features/](docs/features/).
The project's rules are in `.specify/memory/constitution.md`.

## Paid API usage

Any API call that costs the user money (hosted models such as `anthropic:`, AWS, any other paid
service) needs an approved estimate first:

1. **Estimate before starting.** Say what will be called, how many times, and the cost in USD,
   worked out from the last report or the provider's prices. Then stop and wait for a yes.
2. **Hold to the approved estimate.** Spend only what was approved: the cases, model and runs
   named, within the amount.
3. **Stop if the estimate changes.** If the work turns out to need more calls, runs, cases or
   money than approved, or a call costs more than estimated, stop at once and give a new
   estimate. Don't continue until it's approved.
4. **Stop on any API error** (credit, key, rate limit, timeout). Don't retry.

For hosted-model evals the run enforces this: it won't make a paid call without
`AGENT_EVAL_APPROVED_USD` and a price, and stops itself before going over. The details and the
other budget rules (under $0.50 per change unless agreed, only affected cases, once, at most two
runs per change, no repeat runs for stability) are in
[docs/development.md](docs/development.md#the-agent).

## Tests

- Run the full test suite before reporting a task done, and say what passed and what didn't.
- Never hand off a check you could automate: a manual step is only for what a person must judge
  (constitution, Principle V).
- Tests use the scripted model and the pricing fixtures. Live-model evaluations are opt-in and
  paid (see Paid API usage above).

The commands for each suite, what they need, where the tests and pricing fixtures live, and how
to run the app with the scripted model are in [docs/development.md](docs/development.md#tests).

## Documentation

- The README is a fixed orientation page. Don't append feature notes to it; change it only when
  the repo's layout or the getting-started or deploy steps change.
- A feature or fix updates the matching page in `docs/features/` (or the other `docs/` pages it
  affects) and adds a line to `CHANGELOG.md` under the release it ships in.
- `specs/0NN-*/` are the per-feature design records. Don't rewrite them to match later changes.
- `docs/brief/` holds inputs (the original brief, change requests, the standard-architecture
  source). They aren't kept current, so don't describe current behaviour from them.
