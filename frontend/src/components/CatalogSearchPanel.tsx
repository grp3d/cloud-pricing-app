import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { type CatalogSKU, api } from "../api/client";
import { ErrorMessage } from "./ErrorMessage";

interface Props {
  onAdd: (sku: CatalogSKU) => void;
}

// A handful of common attribute keys shown inline in the compact list view, so similar SKUs
// (e.g. several EC2 instance types) can be told apart at a glance (FR-001) without dumping every
// attribute into every row (research.md #2) — the full set is shown at the confirmation step via
// `SkuDetail`. This list is a frontend display choice, not a backend contract: adding another
// common key later doesn't require an API change.
const DETAIL_CANDIDATE_KEYS = [
  "instanceType",
  "memory",
  "vcpu",
  "operatingSystem",
  "storage",
  "group",
  "groupDescription",
];

function detailLine(sku: CatalogSKU): string {
  const parts = DETAIL_CANDIDATE_KEYS.filter((key) => sku.attributes[key]).map(
    (key) => sku.attributes[key],
  );
  return parts.join(" · ");
}

/**
 * AWS catalog search (FR-005): filter by service code, product family, and free text — v1
 * scope only, no attribute-level faceting (spec Assumptions). Requires at least one filter,
 * matching the backend's 400-on-empty-filter behavior, so an empty search never silently
 * tries to browse the full ~173k-row catalog.
 */
export function CatalogSearchPanel({ onAdd }: Props) {
  const [serviceCode, setServiceCode] = useState("");
  const [productFamily, setProductFamily] = useState("");
  const [text, setText] = useState("");

  const hasFilter = Boolean(serviceCode || productFamily || text);

  const search = useQuery({
    queryKey: ["catalog", serviceCode, productFamily, text],
    queryFn: () =>
      api.searchCatalog({ service_code: serviceCode, product_family: productFamily, q: text }),
    enabled: hasFilter,
  });

  return (
    <div aria-label="AWS catalog search">
      <h3>Search AWS services</h3>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          placeholder="Service code (e.g. AmazonEC2)"
          value={serviceCode}
          onChange={(e) => setServiceCode(e.target.value)}
        />
        <input
          placeholder="Product family (e.g. Compute Instance)"
          value={productFamily}
          onChange={(e) => setProductFamily(e.target.value)}
        />
        <input
          placeholder="Search text"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>

      {!hasFilter && <p>Enter at least one filter to search.</p>}
      {search.isLoading && <p>Searching…</p>}
      {search.isError && (
        <ErrorMessage
          message={search.error instanceof Error ? search.error.message : "Search failed."}
          onRetry={() => search.refetch()}
        />
      )}
      {!search.isError && search.data?.results.length === 0 && <p>No matching services found.</p>}

      <ul>
        {search.data?.results.map((r) => {
          const details = detailLine(r);
          return (
            <li key={r.sku}>
              {r.service_name} — {r.product_family} — {r.summary}
              {details && <> — {details}</>}
              {r.unit && <> ({r.unit})</>}
              <button onClick={() => onAdd(r)}>Add</button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
