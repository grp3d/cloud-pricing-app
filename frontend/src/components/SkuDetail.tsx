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
    return <p style={{ color: "#6b7280", fontStyle: "italic" }}>No additional details available.</p>;
  }

  return (
    <dl
      aria-label="Service details"
      style={{
        display: "grid",
        gridTemplateColumns: "max-content 1fr",
        columnGap: 12,
        rowGap: 4,
        margin: "8px 0",
      }}
    >
      {entries.map(([key, value]) => (
        <div key={key} style={{ display: "contents" }}>
          <dt style={{ fontWeight: 600 }}>{key}</dt>
          <dd style={{ margin: 0 }}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
