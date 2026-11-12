"""Azure match rules for the four standard architectures (022-gcp-azure-standard-architectures,
research R1, R4-R6).

Every usage figure of every AWS rule in `match_rules.py` has at least one rule here, naming the
AWS component and figure it stands in for (FR-011). A rule names the exact Azure meter by its
service, product, SKU and meter names plus the published unit, or carries an `omit_reason`.

Owner's rule (research R5): no complex logic to force a mapping. A figure is matched only when
Azure bills the same kind of unit with at most a simple scale (for example a high-availability
standby doubles the vCore-hours); otherwise it is left out with the reason. Figures the AWS
version leaves out are left out too, so the three versions of a design cover the same scope.

Quantities use the shared daily-rate formulas (`quantities.py`).

Edit rules here, then re-run `scripts/resolve_standard_architectures.py --provider azure`;
never hand-edit the generated seed.
"""

from __future__ import annotations

from decimal import Decimal

from scripts.standard_architectures.match_rules import EKS, LAKE, SERVERLESS, WEB
from scripts.standard_architectures.quantities import (
    always_on,
    as_stored,
    daily_dpu,
    monthly,
)
from scripts.standard_architectures.resolver import ProviderRule

# AWS reference region -> Azure region (research R1). Azure's Ireland region (northeurope)
# isn't collected by the pricing pipeline, so westeurope stands in for eu-west-1.
REGIONS = {
    "us-east-1": "eastus",
    "us-west-2": "westus2",
    "eu-west-1": "westeurope",
}

_AS_AWS = "left out to match the AWS version: "
_NO_LCU = (
    "Azure Load Balancer has no LCU-hour unit; it bills data processed (GB), which the "
    "reference doesn't give"
)


def _rule(architecture: str, component: str, figure: str, region: str, unit: str,
          quantity: Decimal, *, service: str, product: str, meter: str,
          sku: str | None = None, **extra) -> ProviderRule:
    filters = {"service_name": service, "product_name": product, "meter_name": meter}
    if sku is not None:
        filters["sku_name"] = sku
    return ProviderRule(
        architecture_id=architecture, component_id=component, figure=figure, region=region,
        filters=filters, expected_unit=unit, quantity=quantity, **extra,
    )


def _omit(architecture: str, component: str, figure: str, region: str, reason: str) -> ProviderRule:
    return ProviderRule(
        architecture_id=architecture, component_id=component, figure=figure, region=region,
        omit_reason=reason,
    )


def _vm(architecture: str, component: str, region: str, count: int, size: str,
        size_note: str) -> ProviderRule:
    """A Linux Dsv5 VM (`azure_vm`, research R6)."""
    return _rule(
        architecture, component, "runningHoursPerMonth", region, "1 Hour", always_on(count),
        service="Virtual Machines", product="Virtual Machines Dsv5 Series",
        meter=size.removeprefix("Standard_").replace("_", " "), sku=size,
        azure_os="linux", size_note=size_note,
    )


def _lb_hours(architecture: str, component: str, region: str) -> ProviderRule:
    return _rule(
        architecture, component, "runningHoursPerMonth", region, "1 Hour", always_on(1),
        service="Load Balancer", product="Load Balancer", sku="Standard",
        meter="Standard Included LB Rules and Outbound Rules",
    )


def _blob(architecture: str, component: str, figure: str, region: str, unit: str,
          quantity: Decimal, meter: str, *, product: str = "General Block Blob v2",
          tier: str = "Hot LRS", **extra) -> ProviderRule:
    return _rule(
        architecture, component, figure, region, unit, quantity,
        service="Storage", product=product, sku=tier, meter=meter, **extra,
    )


_POSTGRES = "Azure Database for PostgreSQL Flexible Server Memory Optimized Edsv5 Series Compute"
_POSTGRES_STORAGE = "Azure Database for PostgreSQL Flex Server Storage"
_LAKE_STORAGE = "Azure Data Lake Storage Gen2 Hierarchical Namespace"


def _postgres(component: str, region: str, note: str) -> ProviderRule:
    return _rule(
        WEB, component, "instance", region, "1 Hour", always_on(1),
        service="Azure Database for PostgreSQL", product=_POSTGRES, sku="4 vCore", meter="vCore",
        size_note="db.r6g.xlarge 4/32 → Flexible Server E4ds_v5 4/32", note=note,
    )


def _postgres_storage(component: str, region: str) -> ProviderRule:
    return _rule(
        WEB, component, "allocatedStorageGB", region, "1 GB/Month", as_stored(250),
        service="Azure Database for PostgreSQL", product=_POSTGRES_STORAGE, sku="Storage",
        meter="Storage Data Stored",
    )


RULES: tuple[ProviderRule, ...] = (
    # ---- Active-Standby Multi-Region Web Application (eastus, westus2) ----
    _rule(WEB, "r53_global_dns", "queriesPerMonth", "eastus", "1M", monthly(10_000_000),
          service="Azure DNS", product="Azure DNS", sku="Public", meter="Public Queries"),
    _omit(WEB, "r53_global_dns", "hostedZones", "eastus", _AS_AWS + "no Route 53 hosted-zone prices"),
    _omit(WEB, "r53_global_dns", "healthChecks", "eastus", _AS_AWS + "no Route 53 health-check prices"),
    _omit(WEB, "cloudfront_cdn", "dataTransferOutGB", "eastus", _AS_AWS + "no CloudFront prices"),
    _omit(WEB, "cloudfront_cdn", "httpRequests", "eastus", _AS_AWS + "no CloudFront prices"),
    _omit(WEB, "cloudfront_cdn", "httpsRequests", "eastus", _AS_AWS + "no CloudFront prices"),
    _lb_hours(WEB, "alb_primary", "eastus"),
    _omit(WEB, "alb_primary", "lcuPerHour", "eastus", _NO_LCU),
    _vm(WEB, "ec2_app_primary", "eastus", 4, "Standard_D4s_v5",
        "4 × t4g.xlarge 4/16 → 4 × D4s_v5 4/16"),
    _postgres("rds_aurora_primary", "eastus", "Aurora's single writer instance"),
    _postgres_storage("rds_aurora_primary", "eastus"),
    _blob(WEB, "s3_primary_bucket", "storageGB", "eastus", "1 GB/Month", as_stored(2000),
          "Hot LRS Data Stored"),
    _blob(WEB, "s3_primary_bucket", "putRequests", "eastus", "10K", monthly(50_000),
          "Hot LRS Write Operations"),
    _blob(WEB, "s3_primary_bucket", "getRequests", "eastus", "10K", monthly(500_000),
          "Hot Read Operations"),
    _rule(WEB, "s3_crr_transfer", "dataTransferGB", "eastus", "1 GB", monthly(250),
          service="Bandwidth", product="Rtn Preference: MGN", sku="Standard",
          meter="Standard Inter-Region Data Transfer"),
    _lb_hours(WEB, "alb_secondary", "westus2"),
    _omit(WEB, "alb_secondary", "lcuPerHour", "westus2", _NO_LCU),
    _vm(WEB, "ec2_app_secondary", "westus2", 4, "Standard_D4s_v5",
        "4 × t4g.xlarge 4/16 → 4 × D4s_v5 4/16"),
    _postgres("rds_aurora_replica", "westus2", "the cross-region read replica"),
    _postgres_storage("rds_aurora_replica", "westus2"),
    _blob(WEB, "s3_dr_bucket", "storageGB", "westus2", "1 GB/Month", as_stored(2000),
          "Hot LRS Data Stored"),
    # ---- Modern Data Lake & ETL Analytics Pipeline (eastus) ----
    _rule(LAKE, "kinesis_stream", "shards", "eastus", "1 Hour", always_on(4),
          service="Event Hubs", product="Event Hubs", sku="Standard",
          meter="Standard Throughput Unit", note="4 shards as 4 throughput units (1 MB/s each)"),
    _omit(LAKE, "kinesis_stream", "putRecordsMB", "eastus",
          "Event Hubs bills ingress per event; the reference gives MB only"),
    _rule(LAKE, "glue_etl_jobs", "dpuCount x executionHoursPerDay", "eastus", "1 Hour",
          daily_dpu(40, 2),
          service="Azure Data Factory v2", product="Azure Data Factory v2 Data Flow - General Purpose",
          sku="vCore", meter="vCore", note="10 DPU x 4 vCPU x 2 h/day = 80 vCore-hours/day"),
    _omit(LAKE, "glue_catalog", "objectsStored", "eastus",
          "no data-catalog service in the confirmed equivalents table"),
    _omit(LAKE, "glue_catalog", "requestsPerMonth", "eastus",
          "no data-catalog service in the confirmed equivalents table"),
    _blob(LAKE, "s3_raw_zone", "storageGB", "eastus", "1 GB/Month", as_stored(10_000),
          "Hot LRS Data Stored", product=_LAKE_STORAGE),
    _blob(LAKE, "s3_analytics_zone", "storageGB", "eastus", "1 GB/Month", as_stored(5_000),
          "Hot LRS Data Stored", product=_LAKE_STORAGE),
    _blob(LAKE, "s3_archive_zone", "storageGB", "eastus", "1 GB/Month", as_stored(50_000),
          "Cold LRS Data Stored", product=_LAKE_STORAGE, tier="Cold LRS",
          note="Glacier Instant Retrieval: the Cold tier, Azure's rarely-read tier with instant access"),
    _rule(LAKE, "athena_query_engine", "dataScannedTBPerMonth", "eastus", "1 TB", monthly(60),
          service="Azure Synapse Analytics", product="Azure Synapse Analytics Serverless SQL Pool",
          sku="Standard", meter="Standard Data Processed"),
    _omit(LAKE, "redshift_serverless", "rpuHoursPerMonth", "eastus",
          "RPU-hours have no like-for-like Azure unit (Synapse dedicated SQL pool DWU-hours "
          "aren't comparable)"),
    # ---- Serverless Microservices Back-End (westeurope) ----
    _omit(SERVERLESS, "cloudfront_edge", "dataTransferOutGB", "westeurope", _AS_AWS + "no CloudFront prices"),
    _omit(SERVERLESS, "cloudfront_edge", "requestsCount", "westeurope", _AS_AWS + "no CloudFront prices"),
    _rule(SERVERLESS, "cognito_user_pools", "monthlyActiveUsers", "westeurope", "1/Month",
          as_stored(10_000),
          service="Azure Active Directory for External Identities",
          product="Azure Active Directory for External Identities", sku="Standard",
          meter="Standard Monthly Active Users"),
    _rule(SERVERLESS, "api_gateway_http", "requestsPerMonth", "westeurope", "10K",
          monthly(20_000_000),
          service="API Management", product="API Management", sku="Consumption",
          meter="Consumption Calls"),
    _rule(SERVERLESS, "lambda_compute", "executionsPerMonth", "westeurope", "10",
          monthly(15_000_000),
          service="Functions", product="Functions", sku="Standard",
          meter="Standard Total Executions"),
    _omit(SERVERLESS, "lambda_compute", "GB-seconds", "westeurope",
          "Azure Functions bills execution time in GB-seconds, a unit the app's pricing engine "
          "doesn't recognize yet"),
    _rule(SERVERLESS, "dynamodb_nosql", "storageGB", "westeurope", "1 GB/Month", as_stored(50),
          service="Azure Cosmos DB", product="Azure Cosmos DB", sku="RUs", meter="Data Stored"),
    _rule(SERVERLESS, "dynamodb_nosql", "readRequestUnits", "westeurope", "1M", monthly(5_000_000),
          service="Azure Cosmos DB", product="Azure Cosmos DB serverless", sku="RUs",
          meter="1M RUs", note="1 RU per read (1 KB item)"),
    _rule(SERVERLESS, "dynamodb_nosql", "writeRequestUnits", "westeurope", "1M",
          monthly(2_000_000 * 5),
          service="Azure Cosmos DB", product="Azure Cosmos DB serverless", sku="RUs",
          meter="1M RUs", note="5 RUs per write (1 KB item)"),
    _rule(SERVERLESS, "sqs_queue", "requestsPerMonth", "westeurope", "1M", monthly(10_000_000),
          service="Service Bus", product="Service Bus", sku="Standard",
          meter="Standard Messaging Operations"),
    _rule(SERVERLESS, "sns_topic", "publishRequestsPerMonth", "westeurope", "100K",
          monthly(2_000_000),
          service="Event Grid", product="Event Grid", sku="Standard", meter="Standard Operations"),
    # ---- Containerized Microservices Platform (EKS) (westus2) ----
    _rule(EKS, "eks_control_plane", "hoursPerMonth", "westus2", "1 Hour", always_on(1),
          service="Azure Kubernetes Service", product="Azure Kubernetes Service", sku="Standard",
          meter="Standard Uptime SLA", note="the AKS Standard tier, billed per cluster-hour"),
    _vm(EKS, "eks_worker_nodes", "westus2", 6, "Standard_D2s_v5",
        "6 × m6i.large 2/8 → 6 × D2s_v5 2/8"),
    _omit(EKS, "fargate_pods", "vCPUPerPod", "westus2",
          "AKS has no per-pod price, and Container Instances isn't in the confirmed table"),
    _omit(EKS, "fargate_pods", "memoryGBPerPod", "westus2",
          "AKS has no per-pod price, and Container Instances isn't in the confirmed table"),
    _rule(EKS, "ecr_repository", "storageGB", "westus2", "1 GB/Month", as_stored(100),
          service="Container Registry", product="Container Registry", sku="Standard",
          meter="Data Stored"),
    _lb_hours(EKS, "nlb_ingress", "westus2"),
    _omit(EKS, "nlb_ingress", "lcuPerHour", "westus2", _NO_LCU),
    _omit(EKS, "app_mesh", "activeMeshes", "westus2", _AS_AWS + "App Mesh has no charge"),
    _rule(EKS, "elasticache_redis", "numNodes", "westus2", "1 Hour", always_on(1),
          service="Redis Cache", product="Azure Redis Cache Standard", sku="C4", meter="C4 Cache",
          size_note="2 × cache.m6g.large 6.38 GiB (primary + replica) → Standard C4 13 GB "
                    "(replica included; C3 is 6 GB)"),
    _rule(EKS, "rds_mysql_primary", "instance", "westus2", "1 Hour", always_on(8),
          service="Azure Database for MySQL",
          product="Azure Database for MySQL Flexible Server General Purpose Ddsv5 Series Compute",
          sku="vCore", meter="vCore",
          size_note="db.m6g.xlarge Multi-AZ 4/16 → Flexible Server D4ds_v5 4/16, zone-redundant HA",
          note="4 vCores x 2 (primary + HA standby) x 24 h/day"),
    _rule(EKS, "rds_mysql_primary", "allocatedStorageGB", "westus2", "1 GB/Month", as_stored(500),
          service="Azure Database for MySQL", product="Azure Database for MySQL Flexible Server Storage",
          sku="Storage", meter="Storage Data Stored"),
    _omit(EKS, "rds_mysql_primary", "provisionedIOPS", "westus2",
          _AS_AWS + "3,000 IOPS is within the AWS gp3 baseline, not billed separately"),
)
