import { describe, expect, it } from "vitest";

import { awsDataTransferLabel } from "../../src/lib/awsDataTransfer";

describe("awsDataTransferLabel", () => {
  it("derives the '{fromRegionCode}=>{toRegionCode}' label for a well-formed AWSDataTransfer SKU", () => {
    const label = awsDataTransferLabel("AWSDataTransfer", {
      fromRegionCode: "us-east-1",
      toRegionCode: "us-west-2-pdx-1",
    });
    expect(label).toBe("us-east-1=>us-west-2-pdx-1");
  });

  it("returns null for a non-AWSDataTransfer service code, even with both region fields present", () => {
    const label = awsDataTransferLabel("AmazonEC2", {
      fromRegionCode: "us-east-1",
      toRegionCode: "us-west-2-pdx-1",
    });
    expect(label).toBeNull();
  });

  it("returns null (not a broken partial string) when fromRegionCode is absent", () => {
    const label = awsDataTransferLabel("AWSDataTransfer", {
      toRegionCode: "us-west-2-pdx-1",
    });
    expect(label).toBeNull();
  });

  it("returns null when toRegionCode is absent", () => {
    const label = awsDataTransferLabel("AWSDataTransfer", {
      fromRegionCode: "us-east-1",
    });
    expect(label).toBeNull();
  });

  it("returns null when a region field is present but empty (research.md §9's real-data shape for internet/CloudFront-bound transfers)", () => {
    const label = awsDataTransferLabel("AWSDataTransfer", {
      fromRegionCode: "",
      toRegionCode: "us-east-1",
    });
    expect(label).toBeNull();
  });

  it("returns null when neither region field is present", () => {
    expect(awsDataTransferLabel("AWSDataTransfer", {})).toBeNull();
  });
});
