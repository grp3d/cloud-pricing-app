import { describe, expect, it } from "vitest";

import { awsDataTransferLabel } from "../../src/lib/awsDataTransfer";
import { buildServicePopupLines, servicePopupAccessibleName } from "../../src/lib/servicePopup";
import { summarizeAttributes } from "../../src/lib/skuDetail";

describe("buildServicePopupLines", () => {
  it("matches the spec's DynamoDB example exactly", () => {
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
      "Operation: PayPerRequestThroughput",
    ]);
  });

  it("omits Operation when empty and UsageType when missing", () => {
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
    expect(lines[2]).toBe(summarizeAttributes(attributes));
    expect(lines).toHaveLength(5);
  });

  it("has no description line when no summary key is present", () => {
    expect(
      buildServicePopupLines({ service_code: "AmazonS3", sku: "S3SKU", attributes: { usagetype: "X" } }),
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
