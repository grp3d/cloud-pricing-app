"""Explicit per-usage-figure match rules for the four standard architectures
(014-architecture-templates-import-export, research.md §3-§5, §7).

Source: `docs/common_aws_architectures.md` (version 1.1). Every usage figure of every component
there has exactly one rule below, in the source's component order. A rule either names the
exact pricing-data SKU filters (service code candidates, product family, exact attribute
equalities, expected On-Demand unit) plus the quantity to enter, or carries an `omit_reason`
explaining why that figure is deliberately left out rather than approximated (Constitution
Principle I, spec FR-010/FR-009a).

Quantities follow the pricing engine's daily-rate convention (research.md §5): `no_period`
units (Hrs, Requests, GB, ...) take a per-day rate; `fixed_period` units (GB-Mo, Obj-Month,
CognitoUserPoolsMAU, ...) take the stored/monthly amount as-is.

This is an explicit, reviewable table — the same "auditable table, never a heuristic" approach
as `src/pricing_data/duration.py`. Edit rules here, then re-run
`scripts/resolve_standard_architectures.py`; never hand-edit the generated seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

_Q = Decimal("0.0001")
_DAYS_PER_MONTH = Decimal(31)  # the pricing engine's fixed month (004, FR-006)
_HOURS_PER_DAY = Decimal(24)
_KINESIS_PAYLOAD_UNIT_KB = Decimal(25)


def _q(value: Decimal) -> Decimal:
    """Round to `SKUSelection.usage_quantity`'s `Numeric(18, 4)`."""
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


# --- Quantity formulas (research.md §5) ----------------------------------------------------


def always_on(count: int | Decimal) -> Decimal:
    """An always-on resource (730 running hours/month in the source) — 24 hours/day each."""
    return _q(Decimal(count) * _HOURS_PER_DAY)


def per_hour_rate(units_per_hour: int | Decimal) -> Decimal:
    """A continuous per-hour rate (e.g. load balancer LCUs) — 24 hours/day."""
    return _q(Decimal(units_per_hour) * _HOURS_PER_DAY)


def monthly(amount_per_month: int | Decimal) -> Decimal:
    """A monthly count (requests, queries, GB transferred, TB scanned) as a daily rate."""
    return _q(Decimal(amount_per_month) / _DAYS_PER_MONTH)


def daily_dpu(dpus: int | Decimal, hours_per_day: int | Decimal) -> Decimal:
    return _q(Decimal(dpus) * Decimal(hours_per_day))


def lambda_gb_seconds(executions_per_month: int, avg_duration_ms: int, memory_mb: int) -> Decimal:
    """Lambda compute: executions x duration (s) x memory (GB), as a daily rate."""
    gb_seconds = (
        Decimal(executions_per_month)
        * (Decimal(avg_duration_ms) / Decimal(1000))
        * (Decimal(memory_mb) / Decimal(1024))
    )
    return _q(gb_seconds / _DAYS_PER_MONTH)


def fargate_vcpu(pods: int, vcpu_per_pod: int | Decimal) -> Decimal:
    return _q(Decimal(pods) * Decimal(vcpu_per_pod) * _HOURS_PER_DAY)


def fargate_gb(pods: int, gb_per_pod: int | Decimal) -> Decimal:
    return _q(Decimal(pods) * Decimal(gb_per_pod) * _HOURS_PER_DAY)


def kinesis_put_payload_units(mb_per_month: int | Decimal) -> Decimal:
    """Kinesis PUT payload units (25 KB chunks) from ingested MB/month, as a daily rate."""
    units = Decimal(mb_per_month) * Decimal(1024) / _KINESIS_PAYLOAD_UNIT_KB
    return _q(units / _DAYS_PER_MONTH)


def as_stored(amount: int | Decimal) -> Decimal:
    """A stored amount or monthly per-unit count billed per month — entered unconverted."""
    return _q(Decimal(amount))


# --- Rules -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchRule:
    architecture_id: str
    component_id: str
    figure: str
    # The VPC region this entry is placed in ("global" components use the architecture's first
    # listed region, FR-006) — also the pricing-data partition searched.
    region: str
    service_codes: tuple[str, ...] = ()
    product_family: str | None = None
    attribute_filters: dict[str, str] = field(default_factory=dict)
    expected_unit: str | None = None
    quantity: Decimal = Decimal(0)
    omit_reason: str | None = None
    note: str | None = None


# EC2 instance filters that isolate the plain Linux, shared-tenancy, on-demand compute SKU from
# its Windows/SQL/dedicated/capacity-reservation siblings.
def _ec2_linux(instance_type: str) -> dict[str, str]:
    return {
        "instanceType": instance_type,
        "operatingSystem": "Linux",
        "tenancy": "Shared",
        "preInstalledSw": "NA",
        "capacitystatus": "Used",
        "licenseModel": "No License required",
    }


_ELB = ("AWSELB", "AmazonEC2")  # AWSELB has no us-east-1 records (research.md §4)
_NO_CLOUDFRONT = (
    "No CloudFront edge data-transfer or request pricing records in the pricing dataset "
    "(only Origin Shield and Lambda@Edge SKUs exist)"
)

WEB = "arch_web_multi_region_active_standby"
LAKE = "arch_data_lake_etl_analytics"
SERVERLESS = "arch_serverless_microservices"
EKS = "arch_containerized_eks_platform"

RULES: tuple[MatchRule, ...] = (
    # ---- Active-Standby Multi-Region Web Application (us-east-1, us-west-2) ----
    MatchRule(WEB, "r53_global_dns", "queriesPerMonth", "us-east-1",
              ("AmazonRoute53",), "DNS Query", {"usagetype": "USE1-DNS-Queries"},
              "Queries", monthly(10_000_000)),
    MatchRule(WEB, "r53_global_dns", "hostedZones", "us-east-1",
              omit_reason="No Route 53 hosted-zone pricing records in the pricing dataset"),
    MatchRule(WEB, "r53_global_dns", "healthChecks", "us-east-1",
              omit_reason="No Route 53 health-check pricing records in the pricing dataset"),
    MatchRule(WEB, "cloudfront_cdn", "dataTransferOutGB", "us-east-1", omit_reason=_NO_CLOUDFRONT),
    MatchRule(WEB, "cloudfront_cdn", "httpRequests", "us-east-1", omit_reason=_NO_CLOUDFRONT),
    MatchRule(WEB, "cloudfront_cdn", "httpsRequests", "us-east-1", omit_reason=_NO_CLOUDFRONT),
    MatchRule(WEB, "alb_primary", "runningHoursPerMonth", "us-east-1",
              _ELB, "Load Balancer-Application", {"usagetype": "LoadBalancerUsage"},
              "Hrs", always_on(1)),
    MatchRule(WEB, "alb_primary", "lcuPerHour", "us-east-1",
              _ELB, "Load Balancer-Application", {"usagetype": "LCUUsage"},
              "LCU-Hrs", per_hour_rate(2)),
    MatchRule(WEB, "ec2_app_primary", "runningHoursPerMonth", "us-east-1",
              ("AmazonEC2",), "Compute Instance", _ec2_linux("t4g.xlarge"), "Hrs", always_on(4)),
    MatchRule(WEB, "rds_aurora_primary", "instance", "us-east-1",
              ("AmazonRDS",), "Database Instance",
              {"usagetype": "InstanceUsage:db.r6g.xl", "databaseEngine": "Aurora PostgreSQL"},
              "Hrs", always_on(1),
              note="Aurora pricing has no Multi-AZ instance attribute (HA comes from replicas); "
                   "matched on the Standard-storage instance SKU"),
    MatchRule(WEB, "rds_aurora_primary", "allocatedStorageGB", "us-east-1",
              ("AmazonRDS",), "Database Storage",
              {"usagetype": "Aurora:StorageUsage", "databaseEngine": "Aurora PostgreSQL"},
              "GB-Mo", as_stored(250)),
    MatchRule(WEB, "s3_primary_bucket", "storageGB", "us-east-1",
              ("AmazonS3",), "Storage", {"usagetype": "TimedStorage-ByteHrs"},
              "GB-Mo", as_stored(2000)),
    MatchRule(WEB, "s3_primary_bucket", "putRequests", "us-east-1",
              ("AmazonS3",), "API Request", {"usagetype": "Requests-Tier1"},
              "Requests", monthly(50_000)),
    MatchRule(WEB, "s3_primary_bucket", "getRequests", "us-east-1",
              ("AmazonS3",), "API Request", {"usagetype": "Requests-Tier2"},
              "Requests", monthly(500_000)),
    MatchRule(WEB, "s3_crr_transfer", "dataTransferGB", "us-east-1",
              ("AWSDataTransfer",), "Data Transfer",
              {"transferType": "InterRegion Outbound", "fromRegionCode": "us-east-1",
               "toRegionCode": "us-west-2", "fromLocationType": "AWS Region",
               "toLocationType": "AWS Region"},
              "GB", monthly(250)),
    MatchRule(WEB, "alb_secondary", "runningHoursPerMonth", "us-west-2",
              _ELB, "Load Balancer-Application", {"usagetype": "USW2-LoadBalancerUsage"},
              "Hrs", always_on(1)),
    MatchRule(WEB, "alb_secondary", "lcuPerHour", "us-west-2",
              _ELB, "Load Balancer-Application", {"usagetype": "USW2-LCUUsage"},
              "LCU-Hrs", per_hour_rate(2)),
    MatchRule(WEB, "ec2_app_secondary", "runningHoursPerMonth", "us-west-2",
              ("AmazonEC2",), "Compute Instance", _ec2_linux("t4g.xlarge"), "Hrs", always_on(4)),
    MatchRule(WEB, "rds_aurora_replica", "instance", "us-west-2",
              ("AmazonRDS",), "Database Instance",
              {"usagetype": "USW2-InstanceUsage:db.r6g.xl", "databaseEngine": "Aurora PostgreSQL"},
              "Hrs", always_on(1)),
    MatchRule(WEB, "rds_aurora_replica", "allocatedStorageGB", "us-west-2",
              ("AmazonRDS",), "Database Storage",
              {"usagetype": "USW2-Aurora:StorageUsage", "databaseEngine": "Aurora PostgreSQL"},
              "GB-Mo", as_stored(250)),
    MatchRule(WEB, "s3_dr_bucket", "storageGB", "us-west-2",
              ("AmazonS3",), "Storage", {"usagetype": "USW2-TimedStorage-ByteHrs"},
              "GB-Mo", as_stored(2000)),
    # ---- Modern Data Lake & ETL Analytics Pipeline (us-east-1) ----
    MatchRule(LAKE, "kinesis_stream", "shards", "us-east-1",
              ("AmazonKinesis",), "Kinesis Streams", {"usagetype": "Storage-ShardHour"},
              "ShardHour", always_on(4)),
    MatchRule(LAKE, "kinesis_stream", "putRecordsMB", "us-east-1",
              ("AmazonKinesis",), "Kinesis Streams", {"usagetype": "PutRequestPayloadUnits"},
              "PutRequest", kinesis_put_payload_units(500_000),
              note="500,000 MB/month converted to 25 KB PUT payload units"),
    MatchRule(LAKE, "glue_etl_jobs", "dpuCount x executionHoursPerDay", "us-east-1",
              ("AWSGlue",), "AWS Glue", {"usagetype": "USE1-ETL-DPU-Hour"},
              "DPU-Hour", daily_dpu(10, 2)),
    MatchRule(LAKE, "glue_catalog", "objectsStored", "us-east-1",
              ("AWSGlue",), "AWS Glue", {"usagetype": "USE1-Catalog-Storage"},
              "Obj-Month", as_stored(10_000)),
    MatchRule(LAKE, "glue_catalog", "requestsPerMonth", "us-east-1",
              ("AWSGlue",), "AWS Glue", {"usagetype": "USE1-Catalog-Request"},
              "Request", monthly(1_000_000)),
    MatchRule(LAKE, "s3_raw_zone", "storageGB", "us-east-1",
              ("AmazonS3",), "Storage", {"usagetype": "TimedStorage-ByteHrs"},
              "GB-Mo", as_stored(10_000)),
    MatchRule(LAKE, "s3_analytics_zone", "storageGB", "us-east-1",
              ("AmazonS3",), "Storage", {"usagetype": "TimedStorage-ByteHrs"},
              "GB-Mo", as_stored(5_000)),
    MatchRule(LAKE, "s3_archive_zone", "storageGB", "us-east-1",
              ("AmazonS3",), "Storage", {"usagetype": "TimedStorage-GIR-ByteHrs"},
              "GB-Mo", as_stored(50_000)),
    MatchRule(LAKE, "athena_query_engine", "dataScannedTBPerMonth", "us-east-1",
              ("AmazonAthena",), "Athena Queries", {"usagetype": "USE1-DataScannedInTB"},
              "Terabytes", monthly(60)),
    MatchRule(LAKE, "redshift_serverless", "rpuHoursPerMonth", "us-east-1",
              ("AmazonRedshift",), "Serverless", {"usagetype": "USE1-Redshift:ServerlessUsage"},
              "RPU-Hr", monthly(240)),
    # ---- Serverless Microservices Back-End (eu-west-1) ----
    MatchRule(SERVERLESS, "cloudfront_edge", "dataTransferOutGB", "eu-west-1",
              omit_reason=_NO_CLOUDFRONT),
    MatchRule(SERVERLESS, "cloudfront_edge", "requestsCount", "eu-west-1",
              omit_reason=_NO_CLOUDFRONT),
    MatchRule(SERVERLESS, "cognito_user_pools", "monthlyActiveUsers", "eu-west-1",
              ("AmazonCognito",), "Amazon Cognito - Lite", {"usagetype": "EU-CognitoLiteMAU"},
              "CognitoUserPoolsMAU", as_stored(10_000)),
    MatchRule(SERVERLESS, "api_gateway_http", "requestsPerMonth", "eu-west-1",
              ("AmazonApiGateway",), "API Calls", {"usagetype": "EU-ApiGatewayHttpRequest"},
              "Requests", monthly(20_000_000)),
    MatchRule(SERVERLESS, "lambda_compute", "executionsPerMonth", "eu-west-1",
              ("AWSLambda",), "Serverless", {"usagetype": "EU-Request-ARM"},
              "Requests", monthly(15_000_000)),
    MatchRule(SERVERLESS, "lambda_compute", "GB-seconds", "eu-west-1",
              ("AWSLambda",), "Serverless", {"usagetype": "EU-Lambda-GB-Second-ARM"},
              "Lambda-GB-Second", lambda_gb_seconds(15_000_000, 250, 1024),
              note="15M executions x 250 ms x 1 GB"),
    MatchRule(SERVERLESS, "dynamodb_nosql", "storageGB", "eu-west-1",
              ("AmazonDynamoDB",), "Database Storage", {"usagetype": "EU-TimedStorage-ByteHrs"},
              "GB-Mo", as_stored(50)),
    MatchRule(SERVERLESS, "dynamodb_nosql", "readRequestUnits", "eu-west-1",
              ("AmazonDynamoDB",), "Amazon DynamoDB PayPerRequest Throughput",
              {"usagetype": "EU-ReadRequestUnits"}, "ReadRequestUnits", monthly(5_000_000)),
    MatchRule(SERVERLESS, "dynamodb_nosql", "writeRequestUnits", "eu-west-1",
              ("AmazonDynamoDB",), "Amazon DynamoDB PayPerRequest Throughput",
              {"usagetype": "EU-WriteRequestUnits"}, "WriteRequestUnits", monthly(2_000_000)),
    MatchRule(SERVERLESS, "sqs_queue", "requestsPerMonth", "eu-west-1",
              ("AWSQueueService",), "API Request",
              {"usagetype": "EU-Requests-Tier1", "queueType": "Standard"},
              "Requests", monthly(10_000_000)),
    MatchRule(SERVERLESS, "sns_topic", "publishRequestsPerMonth", "eu-west-1",
              ("AmazonSNS",), "API Request", {"usagetype": "EU-Requests-Tier1"},
              "Requests", monthly(2_000_000)),
    # ---- Containerized Microservices Platform (EKS) (us-west-2) ----
    MatchRule(EKS, "eks_control_plane", "hoursPerMonth", "us-west-2",
              ("AmazonEKS",), "Compute",
              {"usagetype": "USW2-AmazonEKS-Hours:perCluster", "locationType": "AWS Region"},
              "Hours", always_on(1)),
    MatchRule(EKS, "eks_worker_nodes", "runningHoursPerMonth", "us-west-2",
              ("AmazonEC2",), "Compute Instance", _ec2_linux("m6i.large"), "Hrs", always_on(6)),
    MatchRule(EKS, "fargate_pods", "vCPUPerPod", "us-west-2",
              ("AmazonEKS",), "Compute", {"usagetype": "USW2-Fargate-vCPU-Hours:perCPU"},
              "hours", fargate_vcpu(10, 1)),
    MatchRule(EKS, "fargate_pods", "memoryGBPerPod", "us-west-2",
              ("AmazonEKS",), "Compute", {"usagetype": "USW2-Fargate-GB-Hours"},
              "hours", fargate_gb(10, 2)),
    MatchRule(EKS, "ecr_repository", "storageGB", "us-west-2",
              ("AmazonECR",), "EC2 Container Registry", {"usagetype": "USW2-TimedStorage-ByteHrs"},
              "GB-Mo", as_stored(100)),
    MatchRule(EKS, "nlb_ingress", "runningHoursPerMonth", "us-west-2",
              _ELB, "Load Balancer-Network", {"usagetype": "USW2-LoadBalancerUsage"},
              "Hrs", always_on(1)),
    MatchRule(EKS, "nlb_ingress", "lcuPerHour", "us-west-2",
              _ELB, "Load Balancer-Network", {"usagetype": "USW2-LCUUsage"},
              "LCU-Hrs", per_hour_rate(3)),
    MatchRule(EKS, "app_mesh", "activeMeshes", "us-west-2",
              omit_reason="AWS App Mesh has no direct charge and no pricing records"),
    MatchRule(EKS, "elasticache_redis", "numNodes", "us-west-2",
              ("AmazonElastiCache",), "Cache Instance",
              {"usagetype": "USW2-NodeUsage:cache.m6g.large", "cacheEngine": "Redis"},
              "Hrs", always_on(2)),
    MatchRule(EKS, "rds_mysql_primary", "instance", "us-west-2",
              ("AmazonRDS",), "Database Instance",
              {"usagetype": "USW2-Multi-AZUsage:db.m6g.xl", "databaseEngine": "MySQL",
               "deploymentOption": "Multi-AZ"},
              "Hrs", always_on(1)),
    MatchRule(EKS, "rds_mysql_primary", "allocatedStorageGB", "us-west-2",
              ("AmazonRDS",), "Database Storage",
              {"usagetype": "USW2-RDS:Multi-AZ-GP3-Storage", "databaseEngine": "MySQL",
               "deploymentOption": "Multi-AZ"},
              "GB-Mo", as_stored(500)),
    MatchRule(EKS, "rds_mysql_primary", "provisionedIOPS", "us-west-2",
              omit_reason="3,000 IOPS is within gp3's included baseline, which AWS doesn't bill "
                          "separately (research.md §7.1)"),
)
