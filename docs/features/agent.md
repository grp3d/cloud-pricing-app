# Agent

A logged-in user can ask an agent about their architectures, in a panel under the canvas. In this
version the agent only answers questions; it doesn't change anything.

## What it can do

- Describe the open architecture: its collections and the services in each.
- Give the open architecture's total for 1 day, 1 month (31 days) or 1 year (365 days), and say
  which services drive the cost.
- List the public architectures you can import, grouped by owner with Admin first, as the
  architecture menu's Import does.

Asked to change, create or import something, it says it can't yet and points to where you can do
it. Asked something outside the app (the time, general knowledge), it says it can't help with
that here and what it can help with, rather than answering something else. Asked what it can do,
it lists the above with an example question for each. It sees only what you can see in the app, and treats names and other text inside
architectures as data, never as instructions.

**Figures always come from the pricing engine.** The model never writes an amount itself: it
refers to the figures the pricing operations return, and the app fills them in as USD to 2
decimal places, so they match the Pricing tab. Any amount the model types on its own is shown as
"[figure removed]". Services that can't be priced are named, and the total is said to exclude
them. Every answer with a figure ends with a line the app adds, such as "Prices for 1 month (31
days), snapshot 2026-11-02 r2".

## The panel

- Shown only to logged-in users, never to guests, and only while the agent is switched on. With it
  off, the workspace looks exactly as it does without the agent.
- It starts collapsed to a thin **Agent** bar under the canvas. Open, a bar between the canvas and
  the panel moves (drag it, or use the arrow keys), and the panel's bottom-right corner sets its
  height. Whether it's open, the bar's position and the height are saved to your account.
- **Conversation** and **Activity** switch the panel's view. Answers appear as they're written,
  with a status while the agent is thinking or looking something up.
- When you can't use the agent, the panel says why: your free preview is used up, you've reached
  your monthly limit, or the agent has reached its monthly limit. For a monthly limit it also says
  the date it resets.

## Sessions

- One session per user. **New agent session** starts one; if you already have one, it asks you to
  confirm that the current conversation will be deleted.
- The panel's top right shows when the session started and, beneath it, when it closes: 3 days
  later. At that time the session and its conversation are deleted.
- The session follows whichever architecture is open; each answer is about the one open when you
  sent the message.
- If the model is slow, unreachable or gives an answer the app can't use, the message is marked
  failed with the reason and **Retry** re-sends it. A retry doesn't use another message from your
  allowance. A model call that runs past the timeout setting stops.
- If you leave or reload the page while the agent is answering, the answer still finishes and
  is in the conversation when you come back.

## Activity log

**Activity** lists every operation the agent ran in this session, in order: its name, the inputs
it was given, whether it worked, when, how long it took, and the pricing snapshot behind any
figure.

## Access and limits

- A new user starts with the agent off for them and **3 free preview messages**. Each message uses
  one; at 0 the agent is unavailable to them until the Admin turns it on. Turning the agent off
  for a user also ends their preview.
- Each user has a **monthly message limit** (their own, or the default). Preview messages count
  toward it.
- A **global monthly cap** in USD covers all users, worked out from the hosted model's token
  counts at the rates set by the Admin. A local model costs $0.
- Months are calendar months in UTC; limits reset on the 1st. Once any limit is reached, no
  further model call is made.

The Admin sets all of this on the Admin page (see [admin](admin.md#agent-settings)).

## Models

The model is chosen in Agent settings: **Ollama** (a local model, for example on a laptop) or
**Anthropic** (hosted). The hosted model's API key comes only from the server's environment or,
in the cloud, from SSM; it's never stored in the database or sent to the browser. A hosted model
can't be used until both of its token prices are set. The cloud instance is too small to run a
local model, so there the agent is either off or uses the hosted model.

Every automated test uses a scripted model. Checking real models is a separate run; see
[development.md](../development.md#the-agent).

## Not built yet

Changing, creating and importing architectures through the agent; price comparisons;
cross-cloud translation; an agent for users with no architecture open.

## Specs

[023](../../specs/023-agent-foundation/spec.md)
