# Quickstart: Validate 024 (Agent Pricing Questions and Comparisons)

## Prerequisites

- The dev stack from `docs/development.md`, with the database migrated (`alembic upgrade head`
  in `backend/`; the startup check refuses an old schema).
- Pricing snapshots for AWS, Azure and GCP present locally.
- The agent turned on in Admin → Agent Settings, and for your user. Use Ollama locally, or the
  scripted provider for e2e.

## 1. Automated checks

```bash
cd backend
uv run pytest tests/unit/test_agent_matching.py tests/unit/test_agent_quality.py \
  tests/unit/test_agent_usage_conversion.py tests/unit/test_agent_figures.py
uv run pytest tests/integration/test_agent_compare_operations.py \
  tests/integration/test_agent_results_api.py tests/integration/test_migration_0011.py
uv run pytest tests/agent_evals -k "gc_1"     # gc-10 … gc-17, scripted model
uv run pytest                                  # whole backend suite

cd ../frontend
npm test -- AgentResultsPane agentResults AgentPanel
npx playwright test e2e/agent-results.spec.ts
```

Expected: all pass. The scripted golden conversations GC-1 to GC-8 (cases gc-10 to gc-17)
pass every run (SC-006).

## 2. Opt-in live evaluation

```bash
cd backend
AGENT_EVAL_MODELS="ollama:llama3.1,anthropic:claude-sonnet-5-5" uv run pytest -m live_model
```

Expected: `backend/agent-eval-report.md` lists every 024 case. SC-006 asks for all to pass on
at least two configured models.

## 3. Manual walk-through

1. **Architecture comparison (US2, US6)**
   - Steps: open the AWS "Three-tier web app" standard architecture. In the Agent tab, ask
     "what would this cost on Azure and GCP?"
   - Expected:
     - the agent states its region guesses and on-demand terms;
     - the Results pane opens on the right with AWS, Azure and GCP columns, a match quality
       per row, totals labelled partial if anything is unmatched, and a "Not compared" list;
     - a card appears under the answer;
     - the canvas and Pricing tab are unchanged (SC-007).
   - While it runs, the status reads "Matching services (n of m)…".
   - In the activity log, `find_matches` shows a `duration_ms` under about 10 000 for a
     20-service architecture. That's a target; record the figure you see.
2. **Figures match the engine (SC-001)**
   - Steps: build an Azure architecture with the same picks shown in the table (activity log →
     the `price_matches` summary lists the SKUs) and compare its Pricing tab total.
   - Expected: the totals match to the cent.
3. **Download (FR-020, SC-008)**
   - Steps: select Download CSV and open the file in a spreadsheet tool.
   - Expected: a basis block, then the same rows and totals as the pane; unavailable cells are
     empty with a status, never 0.
4. **Several results**
   - Steps: ask "and on 1-year reserved?"
   - Expected: a second result arrives and the pane shows "Result 2 of 2". ◀ goes back to the
     first, and selecting the first card shows it too.
5. **Divider and narrow layout (FR-018)**
   - Steps: drag the divider, reload the page and reopen the Agent tab. Then split the centre
     column so the Agent tab is under 700 px wide.
   - Expected: the split is kept after the reload. In the narrow tab, Results sits below the
     conversation.
6. **Category comparison (US1)**
   - Steps: ask "How much cheaper is object storage on Azure than GCP?" and answer
     "use defaults".
   - Expected: the defaults and region guesses are stated, a 2-provider result appears, and
     the difference and % are shown.
7. **Honesty (US3, US4)**
   - Steps: ask for a tier with no counterpart, and for a region one provider lacks.
   - Expected:
     - the quality is "partial" or "no equivalent", with the differences;
     - the missing provider is shown "Unavailable" with no figure.
8. **Single price (US5)**
   - Steps: ask "What's the on-demand price of an m5.large in eu-west-1 per month?"
   - Expected: the figure and basis appear in the conversation only, and the pane doesn't open.
9. **No recommendation (FR-016)**
   - Steps: ask "Which cloud is best?"
   - Expected: no provider is recommended, and a specific comparison is offered.
10. **Persistence (FR-021)**
    - Steps: reload the page.
    - Expected: the session's cards and results are still there. Log in as another user: they
      can't fetch the first user's CSV URL (404).
