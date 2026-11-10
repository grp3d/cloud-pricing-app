import { useState } from "react";

import { type CatalogSKU, type DataConnector, type ProviderCode, api } from "../api/client";
import { CatalogSearchPanel } from "./CatalogSearchPanel";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { ErrorMessage } from "./ErrorMessage";
import { PricingInputsForm, type PricingInputs } from "./PricingInputsForm";
import { SkuDetail } from "./SkuDetail";

interface Props {
  connector: DataConnector;
  onChanged: () => void;
  onClose: () => void;
  /** 019 (T054): the architecture's provider; GCP and Azure searches start at data transfer,
   * AWS keeps its data-transfer region fields (`awsDataTransfer.ts`). */
  provider?: ProviderCode;
  /** The connector's "from" region, which every provider prices its data transfer in. */
  region?: string;
}

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

/**
 * Side panel for one Data Connector (FR-009): optionally attach a specific AWS SKU (e.g. a
 * NAT Gateway) representing the connecting service, with its own pricing inputs.
 */
export function DataConnectorPanel({
  connector,
  onChanged,
  onClose,
  provider = "aws",
  region,
}: Props) {
  const [pickedSku, setPickedSku] = useState<CatalogSKU | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  async function attach(inputs: PricingInputs) {
    if (!pickedSku) return;
    try {
      await api.attachConnectorSku(connector.id, {
        service_code: pickedSku.service_code,
        sku: pickedSku.sku,
        ...inputs,
      });
      setError(null);
      setPickedSku(null);
      onChanged();
    } catch (err) {
      setError(errorMessageOf(err));
    }
  }

  async function removeConnector() {
    try {
      await api.deleteConnector(connector.id);
      setConfirmingDelete(false);
      onChanged();
      onClose();
    } catch (err) {
      setConfirmingDelete(false);
      setError(errorMessageOf(err));
    }
  }

  return (
    <aside style={{ border: "1px solid #ccc", padding: 16, marginTop: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <h4>Data Connector</h4>
        <button onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      {error && <ErrorMessage message={error} onRetry={() => setError(null)} />}

      {connector.sku_selection ? (
        <p>
          Attached service: {connector.sku_selection.service_code} / {connector.sku_selection.sku}
          {connector.sku_selection.unit && ` (${connector.sku_selection.unit})`}
        </p>
      ) : (
        <p>No connecting service attached (optional — e.g. a NAT/Internet/Transit Gateway).</p>
      )}

      {pickedSku ? (
        <>
          <p>
            Selected: {pickedSku.service_name} — {pickedSku.summary}
          </p>
          <SkuDetail attributes={pickedSku.attributes} />
          <PricingInputsForm
            onSubmit={attach}
            submitLabel="Attach"
            unit={pickedSku.unit}
            provider={provider}
            priceTypes={pickedSku.price_types}
            kind={pickedSku.kind}
            attributes={pickedSku.attributes}
          />
        </>
      ) : (
        <CatalogSearchPanel
          onAdd={setPickedSku}
          region={region}
          provider={provider}
          defaultKind={provider === "aws" ? undefined : "data_transfer"}
        />
      )}

      <button onClick={() => setConfirmingDelete(true)}>Delete this connector</button>

      {confirmingDelete && (
        <ConfirmDeleteDialog
          itemLabel="this Data Connector"
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={removeConnector}
        />
      )}
    </aside>
  );
}
