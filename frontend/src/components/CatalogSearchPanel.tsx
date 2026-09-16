import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { type CatalogSKU, InvalidRegexPatternError, api } from "../api/client";
import { summarizeAttributes } from "../lib/skuDetail";
import { awsDataTransferLabel } from "../lib/awsDataTransfer";
import { Button } from "./ui/button";
import { ErrorMessage } from "./ErrorMessage";

interface Props {
  onAdd: (sku: CatalogSKU) => void;
  /** 010-multi-region-support, spec FR-005/FR-006: the region search results are scoped to —
   * the selected collection's region, or, for a selected connector, that connector's "from"
   * collection's region. `undefined` disables searching (nothing resolvable to scope it to). */
  region: string | undefined;
}

/** The exact text shown for one result (FR-025) — sorting uses this same string so the
 * displayed order always matches what a user reads, not some hidden field.
 *
 * 009-ui-fixes-next-iteration, US9, FR-027/028: for an `AWSDataTransfer` result, the derived
 * region-pair label replaces `r.summary` (otherwise just its `product_family` again here, with
 * no `instanceType` to fall back to — indistinguishable from every other AWSDataTransfer row);
 * every other service is unaffected (FR-030) since the label is `null` for them. */
function summaryText(r: CatalogSKU): string {
  const details = summarizeAttributes(r.attributes);
  const summary = awsDataTransferLabel(r.service_code, r.attributes) ?? r.summary;
  return `${r.service_name} — ${r.product_family} — ${summary}${
    details ? ` — ${details}` : ""
  }${r.unit ? ` (${r.unit})` : ""}`;
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
 * than wrapping). 008-ui-updates-corrections: no longer renders its own heading — the
 * "Add a Service" section label (FR-009) now comes from the parent `CollectionsPanel`,
 * which is the only place this component is rendered.
 *
 * 008-ui-updates-corrections (US7): each field is now a case-insensitive regex (FR-020,
 * backend-enforced — an ordinary literal string is itself a valid regex, so this is
 * backward-compatible); the filter row + status text stay fixed while only the results list
 * scrolls (FR-022); results are capped at 200 (FR-023) and sorted alphabetically by their
 * own displayed text (FR-025); an "(n of m)" indicator appears when fewer results are shown
 * than actually match (FR-024).
 */
export function CatalogSearchPanel({ onAdd, region }: Props) {
  const [serviceCode, setServiceCode] = useState("");
  const [productFamily, setProductFamily] = useState("");
  const [text, setText] = useState("");
  // 009-ui-fixes-next-iteration, US9, FR-029: dedicated region filters, distinct from the
  // three general fields above, shown only for AWSDataTransfer-relevant searches.
  const [fromRegionCode, setFromRegionCode] = useState("");
  const [toRegionCode, setToRegionCode] = useState("");
  const showRegionFields = /awsdatatransfer/i.test(serviceCode);

  const hasFilter = Boolean(
    serviceCode || productFamily || text || fromRegionCode || toRegionCode,
  );

  const search = useQuery({
    queryKey: ["catalog", region, serviceCode, productFamily, text, fromRegionCode, toRegionCode],
    queryFn: () =>
      api.searchCatalog({
        region: region!,
        service_code: serviceCode,
        product_family: productFamily,
        q: text,
        from_region_code: fromRegionCode,
        to_region_code: toRegionCode,
      }),
    enabled: hasFilter && Boolean(region),
    retry: false, // an invalid regex pattern won't become valid by retrying the same request
  });

  const regexError =
    search.error instanceof InvalidRegexPatternError ? search.error : null;
  const otherError = search.isError && !regexError ? search.error : null;

  const sortedResults = search.data
    ? [...search.data.results].sort((a, b) => summaryText(a).localeCompare(summaryText(b)))
    : [];

  const inputClassName =
    "w-full min-w-0 rounded border border-border bg-background px-1.5 py-1 text-2xs";
  const fieldErrorClassName = "text-2xs text-destructive";

  return (
    <div aria-label="AWS catalog search" className="flex h-full min-h-0 flex-col gap-2">
      {/* Fixed (non-scrolling) filter row + status messages (FR-022) — only the results
          list below scrolls, mirroring 007's FR-004 fixed-top-controls pattern. */}
      <div className="flex shrink-0 flex-col gap-1.5">
        <div>
          <input
            className={inputClassName}
            placeholder="Service code (e.g. AmazonEC2)"
            value={serviceCode}
            onChange={(e) => setServiceCode(e.target.value)}
          />
          {regexError?.field === "service_code" && (
            <p className={fieldErrorClassName}>{regexError.message}</p>
          )}
        </div>
        <div>
          <input
            className={inputClassName}
            placeholder="Product family (e.g. Compute Instance)"
            value={productFamily}
            onChange={(e) => setProductFamily(e.target.value)}
          />
          {regexError?.field === "product_family" && (
            <p className={fieldErrorClassName}>{regexError.message}</p>
          )}
        </div>
        <div>
          <input
            className={inputClassName}
            placeholder="Search text"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {regexError?.field === "text" && (
            <p className={fieldErrorClassName}>{regexError.message}</p>
          )}
        </div>
        {/* 009-ui-fixes-next-iteration, US9, FR-029: dedicated region filters, shown only for
            AWSDataTransfer-relevant searches, distinct from the three general fields above. */}
        {showRegionFields && (
          <>
            <div>
              <input
                className={inputClassName}
                placeholder="From region"
                value={fromRegionCode}
                onChange={(e) => setFromRegionCode(e.target.value)}
              />
              {regexError?.field === "from_region_code" && (
                <p className={fieldErrorClassName}>{regexError.message}</p>
              )}
            </div>
            <div>
              <input
                className={inputClassName}
                placeholder="To region"
                value={toRegionCode}
                onChange={(e) => setToRegionCode(e.target.value)}
              />
              {regexError?.field === "to_region_code" && (
                <p className={fieldErrorClassName}>{regexError.message}</p>
              )}
            </div>
          </>
        )}
      </div>

      {!hasFilter && (
        <p className="shrink-0 text-2xs text-muted-foreground">
          Enter at least one filter to search.
        </p>
      )}
      {search.isLoading && (
        <p className="shrink-0 text-2xs text-muted-foreground">Searching…</p>
      )}
      {otherError && (
        <div className="shrink-0">
          <ErrorMessage
            message={otherError instanceof Error ? otherError.message : "Search failed."}
            onRetry={() => search.refetch()}
          />
        </div>
      )}
      {!search.isError && search.data?.results.length === 0 && (
        <p className="shrink-0 text-2xs text-muted-foreground">No matching services found.</p>
      )}
      {/* 009-ui-fixes-next-iteration, US5, FR-011/012/013: "n of m services displayed" —
          reworded from 008's "(n of m results displayed)" and moved above the results list
          (a fixed element, not inside the scrolling area below) so it's visible without
          scrolling. Hidden entirely at zero total matches (FR-013); red only when the page is
          truncated (n < m, FR-012) — still shown, unstyled, when every match is displayed. */}
      {search.data && search.data.total > 0 && (
        <p
          className={`shrink-0 text-2xs ${
            sortedResults.length < search.data.total
              ? "text-destructive"
              : "text-muted-foreground"
          }`}
        >
          {sortedResults.length} of {search.data.total} services displayed
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        <ul className="flex flex-col gap-1">
          {sortedResults.map((r) => (
            <li
              key={r.sku}
              className="flex items-start justify-between gap-2 rounded border border-transparent px-1 py-1 text-2xs hover:border-border"
            >
              <span className="min-w-0 break-words">{summaryText(r)}</span>
              {/* 009-ui-fixes-next-iteration follow-up: "Edit ->", not "+ Add" -- this button
                  doesn't add the Service to the Architecture yet, only opens it in the Service
                  Editor (column 3) for configuration. "Edit" (not "Configure") per a follow-up
                  request to shrink the button further -- ~58px wide vs. "Configure"'s ~90px. */}
              <Button type="button" size="sm" variant="outline" onClick={() => onAdd(r)}>
                Edit <ArrowRight />
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
