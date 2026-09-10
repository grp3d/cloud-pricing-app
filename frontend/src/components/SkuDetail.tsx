/**
 * Full descriptive detail for one SKU (FR-002): every attribute the AWS Pricing Catalog has for
 * it, as a generic labeled key/value list — no per-service special-casing (research.md #1), so
 * this renders identically for any service or, eventually, any provider (Constitution Principle
 * III). Shown at the "Selected: ..." confirmation step, right before pricing inputs.
 */
interface Props {
  attributes: Record<string, string>;
}

export function SkuDetail({ attributes }: Props) {
  const entries = Object.entries(attributes);

  if (entries.length === 0) {
    return <p className="text-sm italic text-muted-foreground">No additional details available.</p>;
  }

  return (
    // A stacked (label-above-value) layout, not a side-by-side grid: this component now also
    // renders inside the ~260-320px-wide service-configuration panel (007-ui-overhaul-shadcn),
    // and a side-by-side `max-content` label column doesn't respect the container's available
    // width at all — it sizes to the *longest* attribute key across every entry (some AWS
    // attribute keys, e.g. "dedicatedEbsThroughputDescription", are 30+ characters), which
    // overflowed the label column past the panel's own width and squeezed the value column to
    // 0px, rendering every value present in the DOM but invisible (found live). Stacking avoids
    // that whole class of overflow regardless of how narrow the container is.
    <dl aria-label="Service details" className="my-2 min-w-0">
      {entries.map(([key, value]) => (
        <div key={key} className="mb-1.5">
          <dt className="text-xs font-semibold text-muted-foreground">{key}</dt>
          <dd className="m-0 break-words text-sm">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
