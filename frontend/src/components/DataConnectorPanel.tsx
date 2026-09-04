import { useState } from "react";

import { type CatalogSKU, type DataConnector, api } from "../api/client";
import { CatalogSearchPanel } from "./CatalogSearchPanel";
import { PricingInputsForm, type PricingInputs } from "./PricingInputsForm";

interface Props {
  connector: DataConnector;
  onChanged: () => void;
  onClose: () => void;
}

/**
 * Side panel for one Data Connector (FR-009): optionally attach a specific AWS SKU (e.g. a
 * NAT Gateway) representing the connecting service, with its own pricing inputs.
 */
export function DataConnectorPanel({ connector, onChanged, onClose }: Props) {
  const [pickedSku, setPickedSku] = useState<CatalogSKU | null>(null);

  async function attach(inputs: PricingInputs) {
    if (!pickedSku) return;
    await api.attachConnectorSku(connector.id, {
      service_code: pickedSku.service_code,
      sku: pickedSku.sku,
      ...inputs,
    });
    setPickedSku(null);
    onChanged();
  }

  async function removeConnector() {
    await api.deleteConnector(connector.id);
    onChanged();
    onClose();
  }

  return (
    <aside style={{ border: "1px solid #ccc", padding: 16, marginTop: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <h4>Data Connector</h4>
        <button onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      {connector.sku_selection ? (
        <p>
          Attached service: {connector.sku_selection.service_code} / {connector.sku_selection.sku}
        </p>
      ) : (
        <p>No connecting service attached (optional — e.g. a NAT/Internet/Transit Gateway).</p>
      )}

      {pickedSku ? (
        <>
          <p>
            Selected: {pickedSku.service_name} — {pickedSku.summary}
          </p>
          <PricingInputsForm onSubmit={attach} submitLabel="Attach" />
        </>
      ) : (
        <CatalogSearchPanel onAdd={setPickedSku} />
      )}

      <button onClick={removeConnector}>Delete this connector</button>
    </aside>
  );
}
