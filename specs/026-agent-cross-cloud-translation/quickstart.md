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
uv run pytest tests/unit/test_product_keys.py tests/unit/test_translation.py \
  tests/unit/test_seed_mapping_generator.py
uv run pytest tests/integration/test_seed_mappings.py \
  tests/integration/test_agent_translate_operations.py \
  tests/integration/test_agent_translation_api.py tests/integration/test_migration_0013.py
uv run pytest tests/agent_evals -k "GC-32 or GC-33 or GC-34 or GC-35 or GC-36 or GC-37 \
  or GC-38 or GC-39"
uv run pytest                                    # whole backend suite

cd ../frontend
npm test -- TranslationTable translationProposal AgentProposalView
npx playwright test e2e/agent.spec.ts
```

Expected: all pass. Which test covers each acceptance scenario and success criterion is in the
coverage table in [tasks.md](tasks.md#coverage). In short:
- **Seed round trip (SC-006):** translating each AWS standard architecture to 022's regions,
  choosing its partial matches, reproduces 022's GCP and Azure seeds service for service, and
  every figure 022 left out is flagged with 022's reason;
- every source service has exactly one row, matched or flagged (SC-001); partial totals and
  left-out services are disclosed (SC-002);
- every total, difference and percentage equals the engine's to the cent (SC-003);
- the original's saved state is identical across propose, accept, reject, undo and redo (SC-004);
- a partial match, seeded or automatic, is refused unless offered in an earlier message (FR-004);
- a stale translation can't be accepted, in the API and in the browser (FR-012);
- translating from GCP or Azure is declined (FR-011, GC-39);
- finding and proposing a standard architecture's translation takes under 10 s.

## 2. Opt-in live evaluation (paid: ask first)

Claude Haiku 5.5 only (SC-005). Before running, give the estimate and wait for approval
(`CLAUDE.md`, "Paid API usage"). The 2026-11-20 runs cost about $0.011 per case (three runs,
$0.239 in all; see T044 in [tasks.md](tasks.md)).

```bash
cd backend
AGENT_EVAL_MODELS="anthropic:claude-haiku-5-5" AGENT_EVAL_APPROVED_USD=<approved> \
AGENT_EVAL_PRICES="claude-haiku-5-5=0.10/0.50" AGENT_EVAL_MAX_CALLS=<approved calls> \
uv run pytest -m live_model -k "<the cases approved>"
```

Expected: `backend/agent-eval-report.md` shows the cases passing, with calls and cost.

## 3. Manual walk-through: [MANUAL] items only

Everything else is in section 1. These need a person, the real pricing snapshots and the model
you use (about 10 minutes). Under option A (2026-11-20), the agent asks about services with only
partial matches before proposing; that is expected.

1. **Prod Web to Azure.** `[MANUAL: real pricing snapshots and a real model; judging the
   answer and the 5-minute target (SC-007) needs a person]` Open "Active-Standby Multi-Region
   Web Application" (AWS) and ask "Build the equivalent of this in Azure." Answer its questions
   or say "use your defaults". The Application Load Balancers become Application Gateway
   Standard v2 (WAF v2 and Basic v2 offered as alternatives), and their capacity units are
   offered as a partial match. Check: the answer is clear and its caveats are useful, not noise;
   the mapping table reads well (match, quality, origin, differences, both costs); nothing looks
   wrong on the real data (rows left out for an odd reason, unexpected matches). Time from the
   first message to the accepted translation (step 3): under 5 minutes, in at most 3 messages.
2. **Serverless to GCP.** `[MANUAL: real data; whether many partial-match questions are helpful
   or noisy is a judgement]` Open "Serverless Microservices Back-End" (AWS) and ask "Translate
   this to GCP." Most services have only partial matches: check the questions are short and
   understandable, then say "use the partial matches" and check the rows say "Chosen by you".
3. **Accept and undo.** `[MANUAL: real app on real data]` Accept one of the translations: a
   private architecture with the original's name opens under the target provider and looks
   right on the canvas. Undo removes it. The original is unchanged.
