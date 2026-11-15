# Quickstart: Validate 025 (Agent-Built Architectures)

## Prerequisites

- The dev stack from `docs/development.md`, with the database migrated (`alembic upgrade head`
  in `backend/`; migration 0012).
- Pricing snapshots for AWS, Azure and GCP present locally.
- The agent turned on in Admin → Agent Settings, and for your user. Use Ollama locally, or the
  scripted provider for e2e.

## 1. Automated checks (free)

```bash
cd backend
uv run pytest tests/unit/test_architecture_rules.py tests/unit/test_architecture_state.py \
  tests/unit/test_agent_proposals.py
uv run pytest tests/integration/test_agent_change_operations.py \
  tests/integration/test_agent_proposals_api.py tests/integration/test_agent_undo_redo.py \
  tests/integration/test_migration_0012.py
uv run pytest tests/contract tests/integration/test_us1_nest_components.py \
  tests/integration/test_us2_connectors.py   # edit routes unchanged by the rules refactor
uv run pytest tests/agent_evals -k "GC-19 or GC-2"   # gc-19 … gc-28, scripted model
uv run pytest                                    # whole backend suite

cd ../frontend
npm test -- AgentProposalView AgentProposalCard unsavedWork UnsavedWorkDialog
npx playwright test e2e/agent-proposals.spec.ts
```

Expected: all pass. In particular:
- every proposal path leaves the saved architecture unchanged until accept (SC-002);
- accept, undo and redo leave states equal to before / after exactly (SC-004);
- every figure in a proposal equals the engine's (SC-001); every proposal passes the rules
  (SC-003); an agent import equals the menu's Import (SC-005).

## 2. Opt-in live evaluation (paid: ask first)

Claude Haiku 5.5 only (SC-006). Before running, give the estimate and wait for approval
(`CLAUDE.md`, "Paid API usage"). Rough figure from 024's runs: 10 cases × about 6 calls ≈ 60 calls,
about $0.05–0.10 on Haiku.

```bash
cd backend
AGENT_EVAL_MODELS="anthropic:claude-haiku-5-5" AGENT_EVAL_APPROVED_USD=<approved> \
AGENT_EVAL_PRICES="claude-haiku-5-5=0.10/0.50" AGENT_EVAL_MAX_CALLS=80 \
uv run pytest -m live_model -k "GC-19 or GC-2"
```

Expected: `backend/agent-eval-report.md` shows GC-19 to GC-28 passing, with calls and cost.
Local models (`ollama:…`) may be run for information; they aren't required.

## 3. Manual walk-through

1. **Create (US1, SC-007).** With no architecture open, ask "Create a three-tier web app on GCP in
   us-central1." Answer the questions, or say "use your best defaults". Check: at most three
   questions; a proposal in the Results pane with collections, services and connectors, the cost
   by service and region, assumptions with guesses marked; Accept creates it, private, and opens
   it. Time from the first message to the accepted architecture: under 5 minutes, in at most 3
   messages.
2. **Change and replicate (US2, US3).** Open a standard AWS architecture you imported, and ask to
   replicate it to us-west-2. Check: questions about components, standby size and data change;
   the proposal lists additions with before and after cost and the difference; unpriceable
   transfer, if any, is named and the total marked partial.
3. **Reject (GC-6).** Reject a proposal; the architecture is unchanged.
4. **Undo and redo (US4, GC-7).** Accept a proposal of many changes; Undo; the architecture
   matches its previous state, boxes in the same places. Redo; the changes are back.
5. **Manual edit ends undo (GC-8).** Accept, then change a service's quantity by hand. The notice
   appears once, and Undo is gone from the pane and the card.
6. **Stale proposal.** Ask for a change, then edit the architecture by hand before accepting.
   The proposal shows Stale; Accept re-prices and asks again.
7. **Named architecture and unsaved work (FR-017).** Type a quantity in the Service tab without
   saving, then ask "Change 'Prod Web' to use 3 web servers". The dialog appears; check both
   **Save and continue** and **Discard and continue**.
8. **Import (US5, GC-9).** "Import the serverless back-end." Accept; a private copy named "My
   Serverless Microservices Back-End" opens.
9. **Out of scope (GC-10).** "Set up a Kubernetes cost alert." The agent says it can't and lists
   what it can do.
10. **Limits.** With your allowance used up, accept, reject, undo and redo still work.
11. **Performance.** A proposal with about 100 items is built and priced in under 5 s.
