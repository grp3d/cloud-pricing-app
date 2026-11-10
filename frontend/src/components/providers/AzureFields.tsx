import { labelClassName, selectClassName } from "./fieldStyles";

export type AzureOs = "linux" | "windows";

interface Props {
  /** Only virtual machines have an operating system choice (research R6, `azure_vm`). */
  isVm: boolean;
  os: AzureOs;
  onOsChange: (os: AzureOs) => void;
}

/** Azure-only Service Editor fields (019, FR-005a): a VM's operating system, which picks the
 * Linux or Windows meter of the same size. Reservation and savings-plan terms are offered by the
 * common term list from the item's published price types. */
export function AzureFields({ isVm, os, onOsChange }: Props) {
  if (!isVm) return null;
  return (
    <label className={labelClassName}>
      Operating system
      <select
        className={selectClassName}
        value={os}
        onChange={(e) => onOsChange(e.target.value as AzureOs)}
      >
        <option value="linux">Linux</option>
        <option value="windows">Windows</option>
      </select>
    </label>
  );
}
