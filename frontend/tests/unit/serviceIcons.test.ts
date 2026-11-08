import { describe, expect, it } from "vitest";

import { resolveAwsServiceIcon } from "../../src/lib/awsServiceIcons";
import {
  resolveFromMaps,
  resolveServiceIcon,
  type ProviderIconMaps,
} from "../../src/lib/serviceIcons";

// 020 (T016, data-model §5): one entry point for every provider. AWS delegates unchanged; GCP
// and Azure resolve override → service icon → fallback tile, and never an AWS icon.

const GCP_MAPS: ProviderIconMaps = {
  byId: { CE: "Compute-Engine", SQL: "Cloud-SQL" },
  overrides: {
    CE: [
      { match: "Compute > Persistent Disk", icon: "Persistent-Disk" },
      { match: "Compute", icon: "Cloud-GPU" },
    ],
  },
  urlByStem: {
    "Compute-Engine": "/gcp/Compute-Engine.svg",
    "Cloud-SQL": "/gcp/Cloud-SQL.svg",
    "Persistent-Disk": "/gcp/Persistent-Disk.svg",
    "Cloud-GPU": "/gcp/Cloud-GPU.svg",
  },
  logoUrl: "/logos/gcp.png",
};

const AZURE_MAPS: ProviderIconMaps = {
  byId: { VM: "Virtual-Machine", ST: "Storage-Accounts" },
  overrides: { ST: [{ match: "Managed Disks|Ultra Disks", icon: "Disks" }] },
  urlByStem: {
    "Virtual-Machine": "/azure/Virtual-Machine.svg",
    "Storage-Accounts": "/azure/Storage-Accounts.svg",
    Disks: "/azure/Disks.svg",
  },
  logoUrl: "/logos/azure.png",
};

describe("resolveFromMaps (GCP)", () => {
  it("uses the service's icon", () => {
    const icon = resolveFromMaps(
      "gcp",
      { service_code: "SQL", product_family: "Databases" },
      GCP_MAPS,
    );
    expect(icon).toEqual({
      kind: "icon",
      lightUrl: "/gcp/Cloud-SQL.svg",
      darkUrl: "/gcp/Cloud-SQL.svg",
      isFallback: false,
    });
  });

  it("prefers the first matching taxonomy-prefix override (Persistent Disk inside Compute Engine)", () => {
    const disk = resolveFromMaps(
      "gcp",
      { service_code: "CE", product_family: "Compute > Persistent Disk > SSD" },
      GCP_MAPS,
    );
    expect(disk).toMatchObject({ kind: "icon", lightUrl: "/gcp/Persistent-Disk.svg" });
    const gpu = resolveFromMaps(
      "gcp",
      { service_code: "CE", product_family: "Compute > GPUs > On Demand" },
      GCP_MAPS,
    );
    expect(gpu).toMatchObject({ lightUrl: "/gcp/Cloud-GPU.svg" });
    const egress = resolveFromMaps(
      "gcp",
      { service_code: "CE", product_family: "Network > Egress > GCE" },
      GCP_MAPS,
    );
    expect(egress).toMatchObject({ lightUrl: "/gcp/Compute-Engine.svg" });
  });

  it("matches a prefix only at the start of the path", () => {
    const icon = resolveFromMaps(
      "gcp",
      { service_code: "CE", product_family: "Network > Compute > Persistent Disk" },
      GCP_MAPS,
    );
    expect(icon).toMatchObject({ lightUrl: "/gcp/Compute-Engine.svg" });
  });
});

describe("resolveFromMaps (Azure)", () => {
  it("prefers a product-name override (Managed Disks) over the service icon", () => {
    const icon = resolveFromMaps(
      "azure",
      { service_code: "ST", product_family: "Premium SSD Managed Disks" },
      AZURE_MAPS,
    );
    expect(icon).toMatchObject({ kind: "icon", lightUrl: "/azure/Disks.svg" });
  });

  it("matches product-name patterns case-insensitively", () => {
    const icon = resolveFromMaps(
      "azure",
      { service_code: "ST", product_family: "standard hdd managed disks" },
      AZURE_MAPS,
    );
    expect(icon).toMatchObject({ lightUrl: "/azure/Disks.svg" });
  });

  it("uses the service icon when no override matches", () => {
    const icon = resolveFromMaps(
      "azure",
      { service_code: "ST", product_family: "General Block Blob v2" },
      AZURE_MAPS,
    );
    expect(icon).toMatchObject({ lightUrl: "/azure/Storage-Accounts.svg" });
  });
});

describe("resolveFromMaps fallback tile", () => {
  it("names the tile from service_name first", () => {
    const icon = resolveFromMaps(
      "gcp",
      {
        service_code: "MKT",
        product_family: "Marketplace Services > X",
        service_name: "OpenLogic CentOS",
      },
      GCP_MAPS,
    );
    expect(icon).toEqual({
      kind: "fallback",
      provider: "gcp",
      name: "OpenLogic CentOS",
      logoUrl: "/logos/gcp.png",
    });
  });

  it("falls back to the product family, then the service code", () => {
    expect(
      resolveFromMaps("azure", { service_code: "X", product_family: "Some Product" }, AZURE_MAPS),
    ).toMatchObject({ kind: "fallback", provider: "azure", name: "Some Product" });
    expect(
      resolveFromMaps(
        "azure",
        { service_code: "X", product_family: null, service_name: "" },
        AZURE_MAPS,
      ),
    ).toMatchObject({ kind: "fallback", name: "X" });
  });

  it("falls back when a mapped icon has no shipped file", () => {
    const maps = { ...GCP_MAPS, byId: { CE: "Missing-Icon" }, overrides: {} };
    expect(
      resolveFromMaps("gcp", { service_code: "CE", service_name: "Compute Engine" }, maps),
    ).toMatchObject({
      kind: "fallback",
      name: "Compute Engine",
    });
  });
});

describe("resolveServiceIcon", () => {
  it("delegates AWS to resolveAwsServiceIcon with identical results", () => {
    for (const [code, family] of [
      ["AmazonEC2", "Compute Instance"],
      ["AmazonEC2", "NAT Gateway"],
      ["AWSDataTransfer", null],
      ["ZZNotAService", null],
    ] as const) {
      expect(resolveServiceIcon("aws", { service_code: code, product_family: family })).toEqual({
        kind: "icon",
        ...resolveAwsServiceIcon(code, family),
      });
    }
  });

  it("resolves real GCP and Azure services from the generated maps", () => {
    const ce = resolveServiceIcon("gcp", {
      service_code: "6F81-5844-456A",
      product_family: "Compute > GCE > VMs On Demand",
    });
    expect(ce).toMatchObject({ kind: "icon" });
    const disk = resolveServiceIcon("gcp", {
      service_code: "6F81-5844-456A",
      product_family: "Compute > Persistent Disk > SSD",
    });
    expect(disk).toMatchObject({ kind: "icon" });
    expect(disk).not.toEqual(ce);

    const vm = resolveServiceIcon("azure", {
      service_code: "DZH313Z7MMC8",
      product_family: "Virtual Machines Dsv5 Series",
    });
    const managedDisk = resolveServiceIcon("azure", {
      service_code: "DZH317F1HKN0",
      product_family: "Premium SSD Managed Disks",
    });
    expect(vm).toMatchObject({ kind: "icon" });
    expect(managedDisk).toMatchObject({ kind: "icon" });
    expect(managedDisk).not.toEqual(vm);
  });

  it("never returns an AWS icon for GCP or Azure", () => {
    const awsUrls = new Set(
      ["AmazonEC2", "AmazonS3", "ZZNotAService"].flatMap((code) => {
        const icon = resolveAwsServiceIcon(code, null);
        return [icon.lightUrl, icon.darkUrl];
      }),
    );
    for (const provider of ["gcp", "azure"] as const) {
      for (const service_code of ["6F81-5844-456A", "DZH313Z7MMC8", "AmazonEC2", "unknown"]) {
        const icon = resolveServiceIcon(provider, { service_code, product_family: null });
        if (icon.kind === "icon") {
          expect(awsUrls.has(icon.lightUrl)).toBe(false);
          expect(icon.lightUrl).not.toMatch(/aws-icons/);
        } else {
          expect(icon.provider).toBe(provider);
        }
      }
    }
  });
});
