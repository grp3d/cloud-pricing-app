# Quickstart: Validate 026 (Agent Cross-Cloud Translation)

## Prerequisites

- The dev stack from `docs/development.md`, with the database migrated (`alembic upgrade head`
  in `backend/`; migration 0013 adds `service_mappings` and the `translate` proposal kind).
- Pricing snapshots for AWS, GCP and Azure present locally.
- The agent turned on in Admin → Agent Settings, and for your user. Use Ollama locally, or the
  scripted provider for e2e.
- The four AWS standard architectures imported as your own (or use the public ones).

## 1. Automated checks (free)

```bash
cd backend
uv run pytest tests/unit/test_product_keys.py tests/unit/test_translation.py
uv run pytest tests/integration/test_seed_mappings.py \
  tests/integration/test_agent_translate_operations.py \
  tests/integration/test_agent_translation_api.py tests/integration/test_migration_0013.py
uv run pytest tests/agent_evals -k "GC-32 or GC-33 or GC-34 or GC-35 or GC-36 or GC-37 or GC-38"
uv run pytest                                    # whole backend suite

cd ../frontend
npm test -- AgentProposalView AgentProposalCard translation
npx playwright test e2e/agent-translation.spec.ts
```

Expected: all pass. In particular:
- **Seed round trip (SC-006):** translating each AWS standard architecture to 022's regions
  reproduces 022's GCP and Azure seeds, service for service (SKU and quantity), and every figure
  022 left out is flagged with 022's reason;
- every source service has exactly one row, matched or flagged (SC-001); partial totals and
  left-out services are disclosed (SC-002);
- every total, difference and percentage equals the engine's to the cent (SC-003);
- the original's saved state is identical across propose, accept, reject, undo and redo (SC-004);
- a partial candidate is refused unless offered in an earlier message (FR-004);
- a stale translation can't be accepted (FR-012).

## 2. Opt-in live evaluation (paid: ask first)

Claude Haiku 5.5 only (SC-005). Before running, give the estimate and wait for approval
(`CLAUDE.md`, "Paid API usage"). Rough figure from 025's runs ($0.0807 for 11 cases): GC-32 to
GC-38 plus 025's GC-20 and GC-21B, 9 cases with larger operation results, about $0.08–0.15.

```bash
cd backend
AGENT_EVAL_MODELS="anthropic:claude-haiku-5-5" AGENT_EVAL_APPROVED_USD=<approved> \
AGENT_EVAL_PRICES="claude-haiku-5-5=0.10/0.50" AGENT_EVAL_MAX_CALLS=<approved calls> \
uv run pytest -m live_model -k "GC-32 or GC-33 or GC-34 or GC-35 or GC-36 or GC-37 or GC-38 \
  or GC-20 or GC-21B"
```

Expected: `backend/agent-eval-report.md` shows the cases passing, with calls and cost.

## 3. Manual walk-through

1. **Translate (US1, SC-007).** Open "Active-Standby Multi-Region Web Application" (AWS) and ask
   "Build the equivalent of this in Azure." Check: at most three questions (regions offered as
   guesses, term); a proposal in the Results pane with one row per service. Time from the first
   message to the accepted translation: under 5 minutes, in at most 3 messages.
2. **Mapping table (US2).** Each row shows the match, quality, "Seeded" or "Automatic",
   differences and both amounts; CloudFront and the LCU figures are left out with 022's reasons;
   both totals are labelled partial; the difference is "on matched services".
3. **Several equivalents (GC-2).** Translate an architecture with a service that has several
   close candidates; the agent lists them with differences; pick one; the row and cost update.
4. **Partial match (GC-7, FR-004).** Translate an architecture with a service that only has a
   partial candidate. The agent offers it and leaves it out by default. Say "use it"; the row
   shows "Chosen by you"; "which is cheaper?" names it.
5. **Which is cheaper (US6).** Ask; the answer gives both totals, the difference on matched
   services, and every caveat.
6. **Accept, undo, redo, reject (US4).** Accept: a private architecture with the original's name
   opens under Azure. Undo removes it; Redo brings it back. Reject another: nothing is created.
   The original is unchanged throughout.
7. **Stale (FR-012).** Ask for a translation, change the original by hand, then Accept: refused
   with the message to translate again.
8. **Not offered (FR-011).** "Translate this GCP architecture to AWS": the agent says it can't
   yet and lists what it can do.
9. **Performance.** A translation of a standard architecture is found and priced within the
   round limit, in under 10 s on the dev machine.
