import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";

import { type CatalogSKU, api } from "../api/client";
import { summarizeAttributes } from "../lib/skuDetail";
import { Button } from "./ui/button";
import { ErrorMessage } from "./ErrorMessage";

interface Props {
  onAdd: (sku: CatalogSKU) => void;
}

/**
 * AWS catalog search (FR-005): filter by service code, product family, and free text — v1
 * scope only, no attribute-level faceting (spec Assumptions). Requires at least one filter,
 * matching the backend's 400-on-empty-filter behavior, so an empty search never silently
 * tries to browse the full ~173k-row catalog.
 *
 * 007-ui-overhaul-shadcn (US6/T030): the three filter inputs now stack (not a fixed-width
 * row) so they never overflow the ~260-320px workspace column this panel commonly renders
 * inside (found live: the old side-by-side row scrolled the third field out of view rather
 * than wrapping).
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

  const inputClassName =
    "w-full min-w-0 rounded border border-border bg-background px-1.5 py-1 text-sm";

  return (
    <div aria-label="AWS catalog search" className="flex min-w-0 flex-col gap-2">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        <Search className="size-4" /> Search AWS services
      </h3>
      <div className="flex flex-col gap-1.5">
        <input
          className={inputClassName}
          placeholder="Service code (e.g. AmazonEC2)"
          value={serviceCode}
          onChange={(e) => setServiceCode(e.target.value)}
        />
        <input
          className={inputClassName}
          placeholder="Product family (e.g. Compute Instance)"
          value={productFamily}
          onChange={(e) => setProductFamily(e.target.value)}
        />
        <input
          className={inputClassName}
          placeholder="Search text"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>

      {!hasFilter && (
        <p className="text-sm text-muted-foreground">Enter at least one filter to search.</p>
      )}
      {search.isLoading && <p className="text-sm text-muted-foreground">Searching…</p>}
      {search.isError && (
        <ErrorMessage
          message={search.error instanceof Error ? search.error.message : "Search failed."}
          onRetry={() => search.refetch()}
        />
      )}
      {!search.isError && search.data?.results.length === 0 && (
        <p className="text-sm text-muted-foreground">No matching services found.</p>
      )}

      <ul className="flex flex-col gap-1">
        {search.data?.results.map((r) => {
          const details = summarizeAttributes(r.attributes);
          return (
            <li
              key={r.sku}
              className="flex items-start justify-between gap-2 rounded border border-transparent px-1 py-1 text-sm hover:border-border"
            >
              <span className="min-w-0 break-words">
                {r.service_name} — {r.product_family} — {r.summary}
                {details && <> — {details}</>}
                {r.unit && <> ({r.unit})</>}
              </span>
              <Button type="button" size="sm" variant="outline" onClick={() => onAdd(r)}>
                <Plus /> Add
              </Button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
