import { describe, expect, it } from "vitest";

import { awsDataTransferLabel } from "../../src/lib/awsDataTransfer";
import {
  POPUP_ATTRIBUTE_KEYS,
  buildServicePopupLines,
  servicePopupAccessibleName,
} from "../../src/lib/servicePopup";
import { summarizeAttributes } from "../../src/lib/skuDetail";

describe("buildServicePopupLines", () => {
  // 016-canvas-icon-layout, FR-010: no Operation line any more.
  it("matches the spec's DynamoDB example, without an Operation line", () => {
    expect(
      buildServicePopupLines({
        service_code: "AmazonDynamoDB",
        sku: "3ERQSZWPAMX2JWHN",
        attributes: {
          groupDescription: "DynamoDB PayPerRequest Read Request Units",
          usagetype: "EU-ReadRequestUnits",
          operation: "PayPerRequestThroughput",
        },
      }),
    ).toEqual([
      "AmazonDynamoDB",
      "Sku: 3ERQSZWPAMX2JWHN",
      "DynamoDB PayPerRequest Read Request Units",
      "UsageType: EU-ReadRequestUnits",
    ]);
  });

  it("omits UsageType when missing", () => {
    expect(
      buildServicePopupLines({
        service_code: "AmazonDynamoDB",
        sku: "PITRSKU",
        attributes: { operation: "" },
      }),
    ).toEqual(["AmazonDynamoDB", "Sku: PITRSKU"]);
  });

  it("uses today's identifying-detail summary as the description line", () => {
    const attributes = {
      instanceType: "m5.large",
      memory: "8 GiB",
      vcpu: "2",
      usagetype: "BoxUsage:m5.large",
      operation: "RunInstances",
    };
    const lines = buildServicePopupLines({ service_code: "AmazonEC2", sku: "EC2SKU", attributes });
    // 016, FR-011: memory now has its own line, so the summary leaves it out.
    expect(lines[2]).toBe(summarizeAttributes(attributes, { exclude: ["memory"] }));
    expect(lines[2]).not.toContain("8 GiB");
    expect(lines).toEqual([
      "AmazonEC2",
      "Sku: EC2SKU",
      "m5.large · 2",
      "UsageType: BoxUsage:m5.large",
      "memory: 8 GiB",
    ]);
  });

  it("has no description line when no summary key is present", () => {
    expect(
      buildServicePopupLines({
        service_code: "AmazonS3",
        sku: "S3SKU",
        attributes: { usagetype: "X" },
      }),
    ).toEqual(["AmazonS3", "Sku: S3SKU", "UsageType: X"]);
  });

  it("keeps the real SKU for data transfer and adds the region-pair label as its own line", () => {
    const attributes = { fromRegionCode: "us-east-1", toRegionCode: "us-west-2" };
    const lines = buildServicePopupLines({
      service_code: "AWSDataTransfer",
      sku: "DTSKU",
      attributes,
    });
    expect(lines[1]).toBe("Sku: DTSKU");
    expect(lines[2]).toBe(awsDataTransferLabel("AWSDataTransfer", attributes));
  });

  it("never produces an empty or dangling-label line", () => {
    const lines = buildServicePopupLines({
      service_code: "AmazonEC2",
      sku: "X",
      attributes: { usagetype: "", operation: "", groupDescription: "" },
    });
    expect(lines.every((line) => line.trim() !== "" && !line.endsWith(": "))).toBe(true);
  });
});

describe("servicePopupAccessibleName", () => {
  it("joins the lines into one accessible name", () => {
    expect(servicePopupAccessibleName(["AmazonS3", "Sku: X"])).toBe("AmazonS3, Sku: X");
  });
});

// 016-canvas-icon-layout, FR-009: the labeled attribute lines.
describe("labeled attribute lines", () => {
  it("lists the 15 attributes in the spec's order", () => {
    expect(POPUP_ATTRIBUTE_KEYS).toEqual([
      "databaseEngine",
      "processorArchitecture",
      "physicalProcessor",
      "clockSpeed",
      "tenancy",
      "storageType",
      "cacheEngine",
      "networkPerformance",
      "memory",
      "storageMedia",
      "volumeType",
      "minVolumeSize",
      "maxVolumeSize",
      "storageClass",
      "deploymentOption",
    ]);
  });

  it("adds each present attribute on its own line, after UsageType, in list order", () => {
    const lines = buildServicePopupLines({
      service_code: "AmazonRDS",
      sku: "RDSSKU",
      attributes: {
        usagetype: "USE1-Multi-AZUsage:db.m6g.large",
        deploymentOption: "Multi-AZ",
        databaseEngine: "MySQL",
        operation: "CreateDBInstance:0002",
      },
    });
    expect(lines).toEqual([
      "AmazonRDS",
      "Sku: RDSSKU",
      "UsageType: USE1-Multi-AZUsage:db.m6g.large",
      "databaseEngine: MySQL",
      "deploymentOption: Multi-AZ",
    ]);
  });

  it("omits empty attribute values", () => {
    const lines = buildServicePopupLines({
      service_code: "AmazonEC2",
      sku: "X",
      attributes: { tenancy: "", storageType: "gp3" },
    });
    expect(lines).toEqual(["AmazonEC2", "Sku: X", "storageType: gp3"]);
  });
});
