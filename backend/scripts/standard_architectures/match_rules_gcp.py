"""GCP match rules for the four standard architectures (022-gcp-azure-standard-architectures,
research R1, R4-R6).

Every usage figure of every AWS rule in `match_rules.py` has at least one rule here, naming the
AWS component and figure it stands in for (FR-011). A rule names the exact GCP SKU by service and
display name plus the published unit, or carries an `omit_reason`.

Owner's rule (research R5): no complex logic to force a mapping. A figure is matched only when
GCP bills the same kind of unit with at most a simple scale (for example mCPU = vCPU x 1000);
otherwise it is left out with the reason. Figures the AWS version leaves out are left out too,
so the three versions of a design cover the same scope.

Quantities use the shared daily-rate formulas (`quantities.py`). The reference's GB and TB
figures are entered unchanged as GiB and TiB, GCP's units.

Edit rules here, then re-run `scripts/resolve_standard_architectures.py --provider gcp`; never
hand-edit the generated seed.
"""

from __future__ import annotations

from decimal import Decimal

from scripts.standard_architectures.match_rules import EKS, LAKE, SERVERLESS, WEB
from scripts.standard_architectures.quantities import (
    always_on,
    as_stored,
    daily_dpu,
    execution_seconds,
    fargate_gb,
    fargate_vcpu,
    lambda_gb_seconds,
    monthly,
    monthly_tib_from_mb,
)
from scripts.standard_architectures.resolver import GcpMachine, ProviderRule

# AWS reference region -> GCP region (research R1).
REGIONS = {
    "us-east-1": "us-east1",
    "us-west-2": "us-west1",
    "eu-west-1": "europe-west1",
}

_AS_AWS = "left out to match the AWS version: "
_NO_LCU = (
    "GCP load balancers have no LCU-hour unit; they bill data processed (GiB), which the "
    "reference doesn't give"
)
_REGION_NAMES = {"us-east1": "South Carolina (us-east1)", "us-west1": "Oregon (us-west1)"}


def _rule(architecture: str, component: str, figure: str, region: str, service: str,
          display_name: str, unit: str, quantity: Decimal, **extra) -> ProviderRule:
    return ProviderRule(
        architecture_id=architecture,
        component_id=component,
        figure=figure,
        region=region,
        filters={"service_name": service, "display_name": display_name},
        expected_unit=unit,
        quantity=quantity,
        **extra,
    )


def _omit(architecture: str, component: str, figure: str, region: str, reason: str) -> ProviderRule:
    return ProviderRule(
        architecture_id=architecture, component_id=component, figure=figure, region=region,
        omit_reason=reason,
    )


def _e2(architecture: str, component: str, region: str, count: int, vcpus: int,
        memory_gib: int, size_note: str) -> ProviderRule:
    """An E2 machine priced as cores + RAM (`gcp_machine`, research R6)."""
    return _rule(
        architecture, component, "runningHoursPerMonth", region, "Compute Engine",
        "E2 Instance Core running in Americas", "h", always_on(count),
        machine=GcpMachine(
            vcpus=vcpus, memory_gib=Decimal(memory_gib),
            ram_filters={"display_name": "E2 Instance Ram running in Americas"},
        ),
        size_note=size_note,
    )


def _cloud_sql(architecture: str, component: str, region: str, engine: str, availability: str,
               vcpus: int, memory_gib: int, size_note: str, note: str) -> ProviderRule:
    """A Cloud SQL instance priced as vCPUs + RAM through `gcp_machine` (research R6)."""
    prefix = f"Cloud SQL for {engine}: {availability}"
    return _rule(
        architecture, component, "instance", region, "Cloud SQL", f"{prefix} - vCPU in Americas",
        "h", always_on(1),
        machine=GcpMachine(
            vcpus=vcpus, memory_gib=Decimal(memory_gib),
            ram_filters={"display_name": f"{prefix} - RAM in Americas"},
        ),
        size_note=size_note, note=note,
    )


def _alb_hours(architecture: str, component: str, region: str) -> ProviderRule:
    return _rule(
        architecture, component, "runningHoursPerMonth", region, "Networking",
        f"Regional External Application Load Balancer Forwarding Rule Minimum for "
        f"{_REGION_NAMES[region]}", "h", always_on(1),
    )


def _standard_storage(architecture: str, component: str, region: str, gb: int) -> ProviderRule:
    return _rule(
        architecture, component, "storageGB", region, "Cloud Storage",
        "Standard Storage US Regional", "GiBy.mo", as_stored(gb),
    )


_WEB_DB_NOTE = "Aurora's single writer instance: a zonal Cloud SQL instance"

RULES: tuple[ProviderRule, ...] = (
    # ---- Active-Standby Multi-Region Web Application (us-east1, us-west1) ----
    _rule(WEB, "r53_global_dns", "queriesPerMonth", "us-east1", "Cloud DNS",
          "DNS Query (port 53)", "count", monthly(10_000_000)),
    _omit(WEB, "r53_global_dns", "hostedZones", "us-east1", _AS_AWS + "no Route 53 hosted-zone prices"),
    _omit(WEB, "r53_global_dns", "healthChecks", "us-east1", _AS_AWS + "no Route 53 health-check prices"),
    _omit(WEB, "cloudfront_cdn", "dataTransferOutGB", "us-east1", _AS_AWS + "no CloudFront prices"),
    _omit(WEB, "cloudfront_cdn", "httpRequests", "us-east1", _AS_AWS + "no CloudFront prices"),
    _omit(WEB, "cloudfront_cdn", "httpsRequests", "us-east1", _AS_AWS + "no CloudFront prices"),
    _alb_hours(WEB, "alb_primary", "us-east1"),
    _omit(WEB, "alb_primary", "lcuPerHour", "us-east1", _NO_LCU),
    _e2(WEB, "ec2_app_primary", "us-east1", 4, 4, 16, "4 × t4g.xlarge 4/16 → 4 × e2-standard-4 4/16"),
    _cloud_sql(WEB, "rds_aurora_primary", "us-east1", "PostgreSQL", "Zonal", 4, 32,
               "db.r6g.xlarge 4/32 → Cloud SQL Enterprise 4 vCPU / 32 GiB", _WEB_DB_NOTE),
    _rule(WEB, "rds_aurora_primary", "allocatedStorageGB", "us-east1", "Cloud SQL",
          "Cloud SQL for PostgreSQL: Zonal - Standard storage in Americas", "GiBy.mo", as_stored(250)),
    _standard_storage(WEB, "s3_primary_bucket", "us-east1", 2000),
    _rule(WEB, "s3_primary_bucket", "putRequests", "us-east1", "Cloud Storage",
          "Regional Standard Class A Operations", "count", monthly(50_000)),
    _rule(WEB, "s3_primary_bucket", "getRequests", "us-east1", "Cloud Storage",
          "Regional Standard Class B Operations", "count", monthly(500_000)),
    _rule(WEB, "s3_crr_transfer", "dataTransferGB", "us-east1", "Compute Engine",
          "Network Inter Region Data Transfer Out from Americas to Americas", "GiBy", monthly(250)),
    _alb_hours(WEB, "alb_secondary", "us-west1"),
    _omit(WEB, "alb_secondary", "lcuPerHour", "us-west1", _NO_LCU),
    _e2(WEB, "ec2_app_secondary", "us-west1", 4, 4, 16, "4 × t4g.xlarge 4/16 → 4 × e2-standard-4 4/16"),
    _cloud_sql(WEB, "rds_aurora_replica", "us-west1", "PostgreSQL", "Zonal", 4, 32,
               "db.r6g.xlarge 4/32 → Cloud SQL Enterprise 4 vCPU / 32 GiB",
               "the cross-region read replica: a zonal Cloud SQL instance"),
    _rule(WEB, "rds_aurora_replica", "allocatedStorageGB", "us-west1", "Cloud SQL",
          "Cloud SQL for PostgreSQL: Zonal - Standard storage in Americas", "GiBy.mo", as_stored(250)),
    _standard_storage(WEB, "s3_dr_bucket", "us-west1", 2000),
    # ---- Modern Data Lake & ETL Analytics Pipeline (us-east1) ----
    _omit(LAKE, "kinesis_stream", "shards", "us-east1",
          "Pub/Sub has no provisioned-capacity unit like shard-hours; it bills throughput only"),
    _rule(LAKE, "kinesis_stream", "putRecordsMB", "us-east1", "Cloud Pub/Sub",
          "Message Delivery Basic", "TiBy", monthly_tib_from_mb(500_000),
          note="500,000 MB/month of messages as Pub/Sub throughput (TiB)"),
    _rule(LAKE, "glue_etl_jobs", "dpuCount x executionHoursPerDay", "us-east1", "Cloud Dataflow",
          "vCPU Time Batch South Carolina", "h", daily_dpu(40, 2),
          note="10 DPU x 4 vCPU x 2 h/day = 80 vCPU-hours/day"),
    _rule(LAKE, "glue_etl_jobs", "dpuCount x executionHoursPerDay", "us-east1", "Cloud Dataflow",
          "RAM Time South Carolina", "GiBy.h", daily_dpu(160, 2),
          note="10 DPU x 16 GB x 2 h/day = 320 GiB-hours/day"),
    _omit(LAKE, "glue_catalog", "objectsStored", "us-east1",
          "no data-catalog service in the confirmed equivalents table"),
    _omit(LAKE, "glue_catalog", "requestsPerMonth", "us-east1",
          "no data-catalog service in the confirmed equivalents table"),
    _standard_storage(LAKE, "s3_raw_zone", "us-east1", 10_000),
    _standard_storage(LAKE, "s3_analytics_zone", "us-east1", 5_000),
    _rule(LAKE, "s3_archive_zone", "storageGB", "us-east1", "Cloud Storage",
          "Coldline Storage South Carolina", "GiBy.mo", as_stored(50_000),
          note="Glacier Instant Retrieval: Coldline, GCP's rarely-read class with instant access"),
    _rule(LAKE, "athena_query_engine", "dataScannedTBPerMonth", "us-east1", "BigQuery",
          "Analysis (us-east1)", "TiBy", monthly(60)),
    _omit(LAKE, "redshift_serverless", "rpuHoursPerMonth", "us-east1",
          "RPU-hours have no like-for-like GCP unit (BigQuery storage has no AWS figure to size "
          "it from)"),
    # ---- Serverless Microservices Back-End (europe-west1) ----
    _omit(SERVERLESS, "cloudfront_edge", "dataTransferOutGB", "europe-west1", _AS_AWS + "no CloudFront prices"),
    _omit(SERVERLESS, "cloudfront_edge", "requestsCount", "europe-west1", _AS_AWS + "no CloudFront prices"),
    _rule(SERVERLESS, "cognito_user_pools", "monthlyActiveUsers", "europe-west1", "Identity Platform",
          "Tier 1 Monthly Active Users", "count", monthly(10_000)),
    _omit(SERVERLESS, "api_gateway_http", "requestsPerMonth", "europe-west1",
          "no API Gateway call prices in the GCP pricing data (only network egress)"),
    _rule(SERVERLESS, "lambda_compute", "executionsPerMonth", "europe-west1", "Cloud Run Functions",
          "Cloud Run Functions Invocations", "count", monthly(15_000_000)),
    _rule(SERVERLESS, "lambda_compute", "GB-seconds", "europe-west1", "Cloud Run Functions",
          "Cloud Run functions Memory (Request-based billing) in europe-west1", "GiBy.s",
          lambda_gb_seconds(15_000_000, 250, 1024), note="15M executions x 250 ms x 1 GiB"),
    _rule(SERVERLESS, "lambda_compute", "GB-seconds", "europe-west1", "Cloud Run Functions",
          "Cloud Run functions CPU (Request-based billing) in europe-west1", "s",
          execution_seconds(15_000_000, 250), note="15M executions x 250 ms at the default 1 vCPU"),
    _rule(SERVERLESS, "dynamodb_nosql", "storageGB", "europe-west1", "Cloud Firestore",
          "Cloud Firestore Storage Belgium", "GiBy.mo", as_stored(50)),
    _rule(SERVERLESS, "dynamodb_nosql", "readRequestUnits", "europe-west1", "Cloud Firestore",
          "Cloud Firestore Read Ops Belgium", "count", monthly(5_000_000)),
    _rule(SERVERLESS, "dynamodb_nosql", "writeRequestUnits", "europe-west1", "Cloud Firestore",
          "Cloud Firestore Entity Writes Belgium", "count", monthly(2_000_000)),
    _omit(SERVERLESS, "sqs_queue", "requestsPerMonth", "europe-west1",
          "Pub/Sub bills message volume (TiB); the reference gives request counts only"),
    _omit(SERVERLESS, "sns_topic", "publishRequestsPerMonth", "europe-west1",
          "Pub/Sub bills message volume (TiB); the reference gives request counts only"),
    # ---- Containerized Microservices Platform (EKS) (us-west1) ----
    _rule(EKS, "eks_control_plane", "hoursPerMonth", "us-west1", "Kubernetes Engine",
          "Regional Kubernetes Clusters", "h", always_on(1)),
    _e2(EKS, "eks_worker_nodes", "us-west1", 6, 2, 8, "6 × m6i.large 2/8 → 6 × e2-standard-2 2/8"),
    _rule(EKS, "fargate_pods", "vCPUPerPod", "us-west1", "Kubernetes Engine",
          "Autopilot Pod mCPU Requests (us-west1)", "h", fargate_vcpu(10, 1) * 1000,
          note="10 pods x 1 vCPU as GKE Autopilot mCPU-hours (x 1000)"),
    _rule(EKS, "fargate_pods", "memoryGBPerPod", "us-west1", "Kubernetes Engine",
          "Autopilot Pod Memory Requests (us-west1)", "GiBy.h", fargate_gb(10, 2),
          note="10 pods x 2 GiB"),
    _rule(EKS, "ecr_repository", "storageGB", "us-west1", "Artifact Registry",
          "Artifact Registry Storage", "GiBy.mo", as_stored(100)),
    _rule(EKS, "nlb_ingress", "runningHoursPerMonth", "us-west1", "Networking",
          "Regional External Proxy Network Load Balancer Forwarding Rule Minimum for Oregon (us-west1)",
          "h", always_on(1)),
    _omit(EKS, "nlb_ingress", "lcuPerHour", "us-west1", _NO_LCU),
    _omit(EKS, "app_mesh", "activeMeshes", "us-west1", _AS_AWS + "App Mesh has no charge"),
    _rule(EKS, "elasticache_redis", "numNodes", "us-west1", "Cloud Memorystore for Redis",
          "Redis Capacity Standard M2 Iowa/South Carolina/Oregon", "GiBy.h", always_on(7),
          size_note="2 × cache.m6g.large 6.38 GiB (primary + replica) → Standard tier 7 GB "
                    "(replica included)",
          note="7 GB x 24 h/day"),
    _cloud_sql(EKS, "rds_mysql_primary", "us-west1", "MySQL", "Regional", 4, 16,
               "db.m6g.xlarge Multi-AZ 4/16 → Cloud SQL Enterprise HA 4 vCPU / 16 GiB",
               "Multi-AZ: a regional (high-availability) Cloud SQL instance"),
    _rule(EKS, "rds_mysql_primary", "allocatedStorageGB", "us-west1", "Cloud SQL",
          "Cloud SQL for MySQL: Regional - Standard storage in Americas", "GiBy.mo", as_stored(500)),
    _omit(EKS, "rds_mysql_primary", "provisionedIOPS", "us-west1",
          _AS_AWS + "3,000 IOPS is within the AWS gp3 baseline, not billed separately"),
)
