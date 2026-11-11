# Trends

The **Trends** page shows how each provider's list prices move, from the weekly pricing
snapshots. It has two sections, the chart and the biggest movers, each with its own **Reset**.
The last selections in both are saved to your account.

Only on-demand prices are compared, and only for SKUs with a valid, non-zero price at both ends
of a comparison. Prices are shown exactly as published.

## SKUs Changed chart

- For each pair of consecutive weeks, how many SKUs' unit price went **up** and how many went
  **down**, over up to the last 52 weeks. Each selected provider is one up/down pair, combining
  the regions selected for it.
- Choose one or more providers, one or more regions under each, and one category (all
  categories, compute, storage, database or networking; see
  [categories](providers-and-pricing-data.md#categories)).
- Hovering a week shows the counts, each as a % of the SKUs compared, and how many SKUs were
  compared and left out. A week that follows a missing one is marked.
- **Reset**: all providers, all regions, all categories.

## Biggest movers

- For one provider, one category, any regions (none means all) and a period of the last **1,
  4, 13 or 52 weeks** (52 by default, because list prices change rarely).
- Compares each SKU's price in the latest snapshot with its price at the start of the period,
  and lists the **3 largest % increases** and the **3 largest % decreases**. Ties are ranked by
  the size of the price change.
- Each entry shows the service name, SKU description, region, start and end price, unit and %
  change.
- **Reset**: the first available provider, all categories, all regions, 52 weeks.

## The price history

The page reads a history built from the snapshots, stored on the server
(`PRICING_HISTORY_DIR`). It's built at startup and after each snapshot switch, and resumes if
interrupted. While it builds, the page shows "Building history (N of M weeks)". With fewer than
two weekly snapshots it says there isn't enough history yet.

In the cloud the history isn't kept between bring-ups, so it's rebuilt after each `up`. The
first build is the heaviest job the app runs; see
[configuration.md](../configuration.md#trends-price-history).

## Not built

A median weekly % change line and a cumulative change chart were left out of 019, because list
prices change too rarely for them to move. They may come back once real history shows they'd be
useful.

## Specs

[019](../../specs/019-gcp-azure-providers-trends/spec.md) (US2, US3, US4).
