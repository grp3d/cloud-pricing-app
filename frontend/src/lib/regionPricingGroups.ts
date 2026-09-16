/**
 * Pure grouping/subtotal transform for column 5's region-grouped pricing breakdown
 * (010-multi-region-support, spec FR-011/FR-012/FR-014/FR-015, data-model.md's
 * `RegionPricingGroup`). Takes already-priced line items (whatever shape the caller has, as
 * long as it carries `price` and `region`) and returns one group per distinct region, each
 * with its items still in price-descending order and a subtotal — `PricingPanel.tsx` renders
 * one section per group between the existing Total and Data Timestamp lines.
 *
 * Region order: regions appear in the order their own highest-priced item first appears in
 * the overall price-descending sort — so the region containing the single most expensive line
 * item is always the first section (matches the intuitive "put the biggest cost driver first"
 * reading, mirroring the pre-existing flat list's own top-to-bottom ordering).
 *
 * `region: null` (the FR-015 defensive fallback — data-model.md documents this as expected-
 * unreachable given `Collection.region`/`DataConnector.from_collection_id` are both NOT NULL)
 * is grouped under a `"Global"` section rather than dropped or crashing.
 */

export interface RegionPricingGroup<T> {
  region: string;
  items: T[];
  subtotal: number;
}

export function groupLineItemsByRegion<
  T extends { price: string | number; region?: string | null },
>(items: T[]): RegionPricingGroup<T>[] {
  const sorted = [...items].sort((a, b) => Number(b.price) - Number(a.price));

  const order: string[] = [];
  const groups = new Map<string, T[]>();
  for (const item of sorted) {
    const region = item.region ?? "Global";
    if (!groups.has(region)) {
      groups.set(region, []);
      order.push(region);
    }
    groups.get(region)!.push(item);
  }

  return order.map((region) => {
    const groupItems = groups.get(region)!;
    const subtotal = groupItems.reduce((sum, i) => sum + Number(i.price), 0);
    return { region, items: groupItems, subtotal };
  });
}
