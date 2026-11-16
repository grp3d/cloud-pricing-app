# Agent

A logged-in user can ask an agent about their architectures, compare prices across providers,
and have it propose changes, in the Agent tab beside the canvas. The agent never saves anything
itself: every change is a proposal you accept or reject.

## What it can do

- Describe the open architecture: its collections and the services in each.
- Give the open architecture's total for 1 day, 1 month (31 days) or 1 year (365 days), and say
  which services drive the cost.
- List the public architectures you can import, grouped by owner with Admin first, as the
  architecture menu's Import does.
- Compare prices across AWS, Azure and GCP (see [Comparisons](#comparisons)):
  - a kind of service, such as "How much cheaper is object storage on Azure than GCP?";
  - the open architecture, or one category of it, on one or both other providers: "What would
    this cost on Azure?", "on the other two clouds?", "my storage on GCP?";
  - a single price: "What's the on-demand price of an m5.large in eu-west-1 per month?".
- Propose changes (see [Changes](#changes)): create a new architecture ("a three-tier web app on
  GCP in us-central1"); add collections, services and connectors; scale quantities, sizes and
  pricing terms; replicate components to another region; remove components as part of a change;
  import a public architecture as your own private copy.

Asked for anything else (a cost alert, a budget, translating to another provider), it says it
can't and lists what it can do. Asked something outside the app (the time, general knowledge), it says it can't help with
that here and what it can help with, rather than answering something else. Asked what it can do,
it lists the above with an example question for each. It sees only what you can see in the app, and treats names and other text inside
architectures as data, never as instructions.

**Figures always come from the pricing engine.** The model never writes an amount itself: it
refers to the figures the pricing operations return, and the app fills them in as USD to 2
decimal places, so they match the Pricing tab. Any amount the model types on its own is shown as
"[figure removed]". Services that can't be priced are named, and the total is said to exclude
them. Every answer with a figure ends with a line the app adds, such as "Prices for 1 month (31
days), snapshot 2026-11-02 r2".

## Comparisons

A comparison states its **basis**: for each provider the product matched and how closely it
matches, the region, the usage, the duration, the pricing term (on demand unless you choose
another), USD, and that provider's pricing snapshot date.

- **Questions first.** If the price depends on details you didn't give (storage type, tier,
  redundancy, region, amount, term), the agent asks at most three short questions, or uses the
  app's defaults and says which: for example 1 TB stored for a month, or one instance running
  all month. Say "use defaults" to skip the questions.
- **Regions.** A region you name is used. Otherwise the app guesses the nearest region on the
  other provider (the same city where it can, else the nearest in the same part of the world),
  and the agent says it's a guess. You can change it in a follow-up.
- **Matching.** For each product, the app finds the closest products in the same category on the
  other provider; the agent picks among those only. It never names a product itself. For the
  open architecture, every service is matched in one go.
- **Match quality** is set by fixed rules in the app, and the agent may lower it (with a reason)
  but never raise it:
  - **exact**: same kind of product, billing unit and key specifications (vCPU, memory, tier,
    redundancy);
  - **close**: small differences, such as more memory (up to twice), another processor
    architecture, or another redundancy;
  - **partial**: another kind of product, another billing model, fewer resources, a
    different tier, or a different machine type (general purpose vs memory-optimized, GPU,
    confidential), kind of data transfer (internet vs between regions), DNS zone (public vs
    private) or load balancer type (application vs network);
  - **no equivalent**: nothing comparable in the category.

  The differences are listed with each match. Discounts and terms sold as their own product
  (commitments, reservations, savings plans), spot capacity, licences, and developer, free or
  replica variants are never offered as matches; the pricing term is chosen separately.
- **Usage** is carried over only between products billed in the same kind of unit (hours, GB
  stored, GB transferred, requests); GB and GiB count as the same billed unit, as the standard
  architectures use them. GCP machines are sized to the original's vCPU and memory (the
  smallest standard size at least as large). Anything else shows "Can't convert usage", with
  no figure.
- **Nothing is estimated.** A provider, region, product or term that can't be priced is shown
  as unavailable with the reason, and with no figure, difference or percentage. Totals cover
  only the services priced on every side; when any are left out, both totals are labelled
  partial and the left-out services are listed under "Not compared".
- **Follow-ups** ("and for 10 TB?", "what about 1-year reserved?") keep everything else and say
  what changed.
- The agent doesn't recommend a provider; asked which cloud is best, it offers a specific
  comparison instead.
- A comparison never changes or creates an architecture.

### The Results pane

- A comparison's table appears in the **Results** pane to the right of the conversation, drawn
  by the app from the comparison's result. Every figure is the pricing engine's, rounded to the
  cent, and the differences and percentages are computed by the app. The agent's explanation
  stays in the conversation, and a card under the answer names the result ("AWS vs Azure ·
  14 rows · total +12.4%"). A single price has no table.
- The pane opens when a result arrives. **×** closes it; selecting a card shows that result
  again. **◀ ▶** step through the session's results ("Result 2 of 3").
- Drag the divider between the conversation and the pane, or focus it and use the arrow keys,
  to resize them (30–75% for the conversation). The position is saved to your account. When the
  Agent tab is narrower than 700px, the pane sits under the conversation instead.
- Results are kept with the session: reopening it shows the cards, with the pane on the latest
  result. They're deleted with the session, and only you can see them.

### Download CSV

**Download CSV** saves the result shown as a file named like
`comparison-three-tier-web-app-aws-vs-azure-2026-11-13.csv`. It starts with the basis (one line
per provider with region, "(guessed)" where it applies, term and snapshot, then duration,
currency, usage and assumptions), then a blank line, then the table:

- one column group per provider and region: product, match, amount, difference and difference
  %, then a Status column;
- amounts are plain numbers (`1234.56`), rounded like the pane;
- an unavailable or unmatched price is an empty cell with the reason in Status, never 0;
- the last rows are the totals ("Total (partial)" where it applies) and what wasn't compared.

Text that starts like a spreadsheet formula (`=`, `+`, `-`, `@`) is written with a leading `'`,
so names from imported architectures can't run as formulas.

## Changes

- **Questions first.** The agent asks what it needs (provider, regions, sizes, amounts, term,
  which components), at most three short questions, then offers its defaults. Say "use your best
  defaults" and it states every default it used. If you decline both, it proposes nothing and
  says what it needs.
- **A proposal**, not a change. It appears in the Results pane beside the conversation, in the
  same ◀ ▶ sequence as comparison results, with a card under the answer ("Prod Web · 6 changes ·
  +$722.18 (+45.5%)"). The canvas shows only saved work. The proposal lists what will be added,
  changed and removed; the pricing engine's cost before and after (total, difference and
  percentage, by service and by region); each part's share when the request had several, in the
  order applied, so the shares add up to the difference; anything that couldn't be priced (the
  total is then partial); and the agent's assumptions, with guessed regions marked "(guess)". A
  new architecture shows its cost only.
- **The same rules as editing by hand.** A proposal is checked with the editor's own rules
  (nesting, regions, region lock, connectors, price types) and uses only products from the
  catalog; the agent never names a product itself. Something the catalog doesn't have is said and
  left out. A replicated service keeps the original's pricing term unless you ask otherwise. A
  proposal holds at most 100 changes; larger requests are built in parts.
- **Accept or Reject.** Accept saves exactly what was proposed, in one go. For a change, the
  architecture must be the one open; for a new or imported architecture, it opens when you
  accept, private and owned by you. Reject saves nothing. A proposal is **Stale** if the
  architecture changed after it was made: Accept checks it again and re-prices it, and you accept
  the updated figures. A newer proposal in the session replaces a pending one (**Superseded**).
- **Undo and Redo** are on the accepted proposal, in the pane and on its card. Undo puts the
  architecture back exactly as it was before you accepted, box positions included; for a new or
  imported architecture it removes it. Redo applies the change again. One level of each, for the
  latest accepted proposal only. Undo ends, and the panel says so once, when you change the
  architecture yourself (any saved change, renaming included; making it public or private, or
  moving boxes, doesn't count), when you accept a later proposal, when you delete the
  architecture, or when the session ends.
- **Refinements and what-ifs.** "Make the standby half the size" updates the pending proposal and
  says what changed. "What if I doubled the storage?" is a proposal you don't have to accept.
- **Another architecture.** Name one of yours and the agent opens it. If the open one has unsaved
  Service tab input, you're asked first: **Save and continue** or **Discard and continue**.
- **Import** proposes "My <name>"; accepting makes the same private copy the menu's Import does.
- Accept, Reject, Undo and Redo make no model call and use no message from your allowance, so they
  work after a limit is reached. They wait while the agent is answering. They appear in the
  activity log as your actions.

## The Agent tab

- The agent is the **Agent** tab beside **Canvas** in the centre column. The two tabs merge,
  split and swap like the inspector's Pricing and Service tabs (see
  [workspace and preferences](workspace-and-preferences.md)); the arrangement is saved to your
  account. Canvas is in front by default; to keep the agent in view, move Agent to the lower
  half.
- Usable only by logged-in users while the agent is switched on. For a guest, or with the agent
  off, the Agent tab is shown but inactive, and its tooltip says why.
- **Conversation** and **Activity** switch the panel's view. Answers appear as they're written,
  with a status while the agent is thinking or looking something up. While it matches an
  architecture's services, the status counts them: "Matching services (12 of 20)…".
- When you can't use the agent, the panel says why: your free preview is used up, you've reached
  your monthly limit, or the agent has reached its monthly limit. For a monthly limit it also says
  the date it resets.
- When an answer fails, the panel says what went wrong as precisely as it can: the model's
  account is out of credit, the model rejected its API key (both need an Admin), the model is
  limiting requests (try again in a minute), it can't be reached, or it took too long. If the
  model writes out an operation instead of running it, as weaker local models sometimes do, the
  answer isn't shown: the panel says the model gave an answer the app couldn't use.

## Sessions

- One session per user. **New agent session** starts one; if you already have one, it asks you to
  confirm that the current conversation will be deleted.
- The panel's top right shows when the session started and, beneath it, when it closes: 3 days
  later. At that time the session and its conversation are deleted.
- The session follows whichever architecture is open; each answer is about the one open when you
  sent the message.
- If the model is slow, unreachable or gives an answer the app can't use, the message is marked
  failed with the reason and **Retry** re-sends it. A retry doesn't use another message from your
  allowance. A model call that runs past the timeout setting stops. So does an operation (for
  example matching a large architecture): the agent then says it couldn't finish and offers
  something smaller, and the answer still completes.
- If you leave or reload the page while the agent is answering, the answer still finishes and
  is in the conversation when you come back.

## Activity log

**Activity** lists every operation the agent ran in this session, in order: its name, the inputs
it was given, whether it worked (or was stopped for taking too long), when, how long it took,
and the pricing snapshot behind any figure. For comparisons the summary names the regions, the
products priced (by SKU) and the result. Your decisions on proposals (accept, reject, undo,
redo) are listed too, as yours.

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

Building or saving a comparison as an architecture on another provider (cross-cloud
translation); reviewed cross-provider mappings (until then the app's candidates and quality rules decide); download
formats other than CSV; an agent for users with no architecture open.

## Specs

[023](../../specs/023-agent-foundation/spec.md),
[024](../../specs/024-agent-pricing-questions/spec.md),
[025](../../specs/025-agent-architecture-changes/spec.md)
