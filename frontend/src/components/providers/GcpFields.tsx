import { inputClassName, labelClassName } from "./fieldStyles";

interface Props {
  /** A predefined machine family's core SKU with its matching RAM SKU (research R6). */
  isMachine: boolean;
  vcpus: string;
  memoryGib: string;
  onVcpusChange: (value: string) => void;
  onMemoryGibChange: (value: string) => void;
}

/** GCP-only Service Editor fields (019, FR-005a): a machine's vCPUs and memory, priced as
 * vCPUs × core rate + GiB × RAM rate. Commitment terms are offered by the common term list from
 * the item's published price types. */
export function GcpFields({
  isMachine,
  vcpus,
  memoryGib,
  onVcpusChange,
  onMemoryGibChange,
}: Props) {
  if (!isMachine) return null;
  return (
    <div className="flex gap-2">
      <label className={labelClassName}>
        vCPUs
        <input
          className={inputClassName}
          type="number"
          min="1"
          step="1"
          value={vcpus}
          onChange={(e) => onVcpusChange(e.target.value)}
        />
      </label>
      <label className={labelClassName}>
        Memory (GiB)
        <input
          className={inputClassName}
          type="number"
          min="0"
          step="any"
          value={memoryGib}
          onChange={(e) => onMemoryGibChange(e.target.value)}
        />
      </label>
    </div>
  );
}
