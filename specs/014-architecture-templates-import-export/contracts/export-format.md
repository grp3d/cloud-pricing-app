# Contract: Architecture Export File (format version 1)

This is the only file format the Admin tab's Export produces and Import accepts. The checked-in standard-architecture seed (`backend/src/db/seed/standard_architectures.json`) uses the same format. Field-level rules are in [../data-model.md](../data-model.md#architecture-export-file-transfer-document-not-persisted).

## Example

```json
{
  "format": "cloud-pricing-architectures",
  "format_version": 1,
  "exported_at": "2026-09-25T14:30:22Z",
  "source_username": "jdoe",
  "architectures": [
    {
      "name": "Web App",
      "provider": "aws",
      "collections": [
        {
          "ref": "c1", "type": "vpc", "name": "VPC (us-east-1)", "region": "us-east-1",
          "parent_ref": null,
          "sku_selections": [
            { "service_code": "AmazonEC2", "sku": "D3A672YT5C38ZG9H",
              "pricing_term": "on_demand", "purchase_option": "not_applicable",
              "usage_quantity": "96.0000" }
          ]
        },
        {
          "ref": "c2", "type": "application_component", "name": "Web tier",
          "region": "us-east-1", "parent_ref": "c1", "sku_selections": []
        },
        {
          "ref": "c3", "type": "vpc", "name": "VPC (us-west-2)", "region": "us-west-2",
          "parent_ref": null, "sku_selections": []
        }
      ],
      "connectors": [
        { "from_ref": "c1", "to_ref": "c3",
          "sku_selection": { "service_code": "AWSDataTransfer", "sku": "…",
                             "pricing_term": "on_demand", "purchase_option": "not_applicable",
                             "usage_quantity": "8.0645" } }
      ]
    }
  ]
}
```

## Rules

- **Discriminator.** `format` MUST equal `"cloud-pricing-architectures"`, and `format_version` MUST be one of the supported versions (currently `{1}`). Anything else is a whole-file failure.
- **`usage_quantity` is serialized as a decimal string.** This preserves `Numeric(18, 4)` exactly, the same way Pydantic `Decimal` serializes elsewhere in this API. Import also accepts a JSON number.
- **Order.** Collections are serialized with every parent before its children, matching the existing `created_at` order, and SKU selections keep their creation order. Import creates rows in file order, so a re-exported architecture shows services in the same order (SC-004).
- **`ref`s are file-local.** Export assigns `c1`, `c2`, … per architecture. They are not database ids.
- **Unknown extra fields** at any level are ignored, which leaves room for later non-breaking additions. A breaking change bumps `format_version`.
- **Provider** is carried per architecture (Constitution III). Import doesn't check provider-specific pricing data for anything other than `aws` today, because only AWS pricing data exists. A non-`aws` entry fails with `Provider not supported: gcp`.
