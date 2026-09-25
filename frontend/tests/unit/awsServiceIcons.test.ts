import { describe, expect, it } from "vitest";

import { resolveAwsServiceIcon } from "../../src/lib/awsServiceIcons";
import {
  AWS_DATA_TRANSFER_ICON,
  AWS_FALLBACK_ICON,
  AWS_SERVICE_ICON_BY_CODE,
  AWS_SERVICE_ICON_BY_CODE_AND_FAMILY,
} from "../../src/lib/awsServiceIcons.generated";

const shippedStems = new Set(
  Object.keys(import.meta.glob("../../src/assets/aws-icons/*.svg")).map((path) =>
    path.replace(/^.*\//, "").replace(/\.svg$/, ""),
  ),
);

describe("resolveAwsServiceIcon", () => {
  it("resolves a service code to its own icon", () => {
    const icon = resolveAwsServiceIcon("AmazonDynamoDB", null);
    expect(icon.lightUrl).toContain("Amazon-DynamoDB");
    expect(icon.darkUrl).toBe(icon.lightUrl);
    expect(icon.isFallback).toBe(false);
  });

  it("prefers a (service code, product family) override over the service-code icon", () => {
    expect(resolveAwsServiceIcon("AmazonEC2", "NAT Gateway").lightUrl).toContain(
      "Amazon-Virtual-Private-Cloud",
    );
  });

  it("falls back to the service-code icon for a product family with no override", () => {
    const icon = resolveAwsServiceIcon("AmazonEC2", "Compute Instance");
    expect(icon.lightUrl).toMatch(/Amazon-EC2[.-]/);
    expect(icon.isFallback).toBe(false);
  });

  it("uses the theme-aware Data Stream icon for AWSDataTransfer", () => {
    const icon = resolveAwsServiceIcon("AWSDataTransfer", "Data Transfer");
    expect(icon.lightUrl).toContain("Data-Stream_Light");
    expect(icon.darkUrl).toContain("Data-Stream_Dark");
    expect(icon.isFallback).toBe(false);
  });

  it("returns the theme-aware fallback icon for an unknown service", () => {
    const icon = resolveAwsServiceIcon("NotARealService", null);
    expect(icon.isFallback).toBe(true);
    expect(icon.lightUrl).toContain("AWS-Cloud-logo");
    expect(icon.darkUrl).toContain("AWS-Cloud-logo_Dark");
    expect(icon.darkUrl).not.toBe(icon.lightUrl);
  });

  it("is deterministic", () => {
    expect(resolveAwsServiceIcon("AmazonEC2", "Storage")).toEqual(
      resolveAwsServiceIcon("AmazonEC2", "Storage"),
    );
  });
});

describe("generated icon map integrity", () => {
  it("ships an SVG for every icon stem the map references", () => {
    const referenced = [
      ...Object.values(AWS_SERVICE_ICON_BY_CODE),
      ...Object.values(AWS_SERVICE_ICON_BY_CODE_AND_FAMILY).flatMap((m) => Object.values(m)),
      AWS_FALLBACK_ICON.light,
      AWS_FALLBACK_ICON.dark,
      AWS_DATA_TRANSFER_ICON.light,
      AWS_DATA_TRANSFER_ICON.dark,
    ];
    expect(referenced.filter((stem) => !shippedStems.has(stem))).toEqual([]);
  });
});
