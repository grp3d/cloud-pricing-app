# Quickstart: Agent Foundation

How to check the feature works end to end. Endpoints are in
[contracts/agent-api.md](./contracts/agent-api.md); tables in [data-model.md](./data-model.md).

## Prerequisites

- Local dev stack as in `docs/development.md` (Postgres, `PRICING_DATA_URI` pointing at
  `_DATA-PIPELINE`), with `uv run alembic upgrade head` run (adds revision 0010).
- For a local model: Ollama running (`ollama serve`) with a tool-capable model pulled, for
  example `ollama pull llama3.1`.
- For a hosted model: `AGENT_ANTHROPIC_API_KEY` set in `backend/.env`.
- A named user other than Admin (create one on the Admin page).

## 1. Automated tests (no network)

```bash
cd backend && uv run pytest                      # includes the scripted golden conversations
cd frontend && npm test && npm run test:e2e      # agent off by default: existing e2e unchanged
```

Expected: all pass; no test contacts a model (SC-002, FR-025).

## 2. Agent off (the default)

Start the app. The workspace looks exactly as before: no panel under the canvas, for every user
(clarification 4).

## 3. Settings without a redeploy (Story 5)

1. As Admin, open Admin → Agent settings. `API key set` shows yes or no, never the key.
2. Try to switch the agent on with no model: refused with a message.
3. Set provider `ollama`, model `llama3.1`, switch on, save.
4. Try a timeout of 0 or a negative cap: refused, the old value stays.

## 4. Preview and limits (Story 6)

1. Log in as the named user. The collapsed agent bar appears under the canvas. Open it, press
   **New agent session**: the start and close times (start + 3 days) show top right.
2. Send three messages. The preview counter drops 3 → 0. The fourth is refused: "preview used".
3. As Admin, turn the agent on for that user and set their monthly limit to 5. The user table
   shows `3 of 5` this month. Send two more, then a third: refused, "monthly limit reached",
   with the reset date (the 1st of next month).
4. Set the global cap to 0.00: any user's next message is refused with the global-cap message.

## 5. Answers (Stories 1 and 2)

With the Admin's standard "Active-Standby Multi-Region Web Application" imported and open:

1. "What does this architecture cost per month?" → the 1-month total, stated as 31 days, with
   the snapshot date; equal to the Pricing tab's 1-month total to the cent.
2. "What's driving the cost?" → the largest services with figures.
3. "What can I import?" → the Import list, grouped by owner, Admin first.
4. "Import the Serverless architecture for me" → declined; points to Import.
5. Open the activity log: each operation with inputs, outcome and snapshot date.

## 6. Failures (Story 4)

1. Stop Ollama and send a message: "unavailable" with **Retry**; the rest of the app works.
2. Set the timeout to 5 seconds with a slow model: the message stops with a timeout and Retry;
   retrying doesn't use another input (the user table count is unchanged).

## 7. Layout (clarification 1)

Drag the bar between canvas and panel, resize the panel from its bottom-right corner, collapse
it, reload, and log in on another browser: the same layout returns.

## 8. Live evaluation (opt-in)

```bash
cd backend
AGENT_EVAL_MODELS="ollama:llama3.1,anthropic:claude-haiku-5-5" uv run pytest -m live_model
```

Expected: `backend/agent-eval-report.md` with pass/fail per case for each model (SC-005).
