"""Product profiles (024, research R2): function, category, specs and billing unit kind from a
catalog item, by fixed per-provider tables. Unknown facts are left out, never guessed."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agent.matching.profiles import product_label, profile, unit_kind
from src.pricing_data.providers.base import CatalogItem


def aws(code, family, **attrs) -> CatalogItem:
    return CatalogItem(provider="aws", service_code=code, service_name=None,
                       product_family=family, sku="SKU", summary="", attributes=attrs, unit=None)


def azure(kind, service, unit, **attrs) -> CatalogItem:
    return CatalogItem(provider="azure", service_code="X", service_name=service,
                       product_family=attrs.get("product_name"), sku="A/B/C", summary="",
                       attributes=attrs, unit=unit, kind=kind)


def gcp(kind, taxonomy, summary, unit) -> CatalogItem:
    return CatalogItem(provider="gcp", service_code="S", service_name="Svc",
                       product_family=taxonomy, sku="1-2-3", summary=summary, attributes={},
                       unit=unit, kind=kind)


def test_aws_ec2_instance():
    p = profile(aws("AmazonEC2", "Compute Instance", instanceType="t4g.xlarge", vcpu="4",
                    memory="16 GiB", operatingSystem="Linux"), unit="Hrs")
    assert (p.function, p.category, p.unit_kind) == ("vm", "compute", "hour")
    assert p.specs == {"vcpu": 4, "memory_gib": Decimal(16), "arch": "arm", "burstable": True,
                       "purpose": "general", "os": "linux"}


def test_aws_x86_instance_and_rds():
    assert profile(aws("AmazonEC2", "Compute Instance", instanceType="m6i.large", vcpu="2",
                       memory="8 GiB")).specs["arch"] == "x86"
    p = profile(aws("AmazonRDS", "Database Instance", instanceType="db.r6g.xlarge", vcpu="4",
                    memory="32 GiB", databaseEngine="Aurora PostgreSQL",
                    deploymentOption="Multi-AZ"), unit="Hrs")
    assert (p.function, p.category) == ("managed_db", "database")
    assert p.specs == {"vcpu": 4, "memory_gib": Decimal(32), "arch": "arm", "burstable": False,
                       "purpose": "memory", "engine": "postgresql", "ha": True}


@pytest.mark.parametrize(("storage_class", "klass"), [
    ("General Purpose", "hot"), ("Infrequent Access", "cool"),
    ("Archive Instant Retrieval", "cold"), ("Glacier Deep Archive", "archive"),
])
def test_aws_s3_storage_classes(storage_class, klass):
    p = profile(aws("AmazonS3", "Storage", storageClass=storage_class), unit="GB-Mo")
    assert (p.function, p.unit_kind) == ("object_storage", "gb_month")
    assert p.specs["storage_class"] == klass


def test_aws_s3_requests_and_load_balancer_capacity():
    assert profile(aws("AmazonS3", "API Request", group="S3-API-Tier1")).function == (
        "object_requests_write")
    assert profile(aws("AmazonS3", "API Request", group="S3-API-Tier2")).function == (
        "object_requests_read")
    assert profile(aws("AWSELB", "Load Balancer-Application",
                       usagetype="USW2-LCUUsage")).function == "load_balancer_capacity"


def test_azure_vm_specs_from_the_size_name():
    p = profile(azure("vm", "Virtual Machines", "1 Hour", product_name="Virtual Machines Dsv5 "
                      "Series", sku_name="Standard_D4s_v5", arm_sku_name="Standard_D4s_v5"))
    assert (p.function, p.unit_kind) == ("vm", "hour")
    assert p.specs == {"vcpu": 4, "memory_gib": Decimal(16), "arch": "x86", "burstable": False,
                       "purpose": "general"}


def test_azure_vm_family_without_a_memory_ratio_has_no_memory_spec():
    p = profile(azure("vm", "Virtual Machines", "1 Hour", arm_sku_name="Standard_B2s"))
    assert p.specs == {"vcpu": 2, "arch": "x86", "burstable": True, "purpose": "general"}
    # "m" (more memory) and "l" (low memory) say the ratio: B2ms is 8 GiB, D4ls_v5 is 8 GiB.
    assert profile(azure("vm", "Virtual Machines", "1 Hour", arm_sku_name="Standard_B2ms")
                   ).specs["memory_gib"] == Decimal(8)
    assert profile(azure("vm", "Virtual Machines", "1 Hour", arm_sku_name="Standard_D4ls_v5")
                   ).specs["memory_gib"] == Decimal(8)


def test_azure_blob_storage_class_and_redundancy():
    p = profile(azure("object_storage", "Storage", "1 GB/Month",
                      product_name="General Block Blob v2", sku_name="Hot LRS",
                      meter_name="Hot LRS Data Stored"))
    assert (p.function, p.unit_kind) == ("object_storage", "gb_month")
    assert p.specs == {"storage_class": "hot", "redundancy": "local"}


def test_azure_database_compute_and_storage():
    compute = profile(azure("managed_db", "Azure Database for PostgreSQL", "1 Hour",
                            product_name="Azure Database for PostgreSQL Flexible Server Memory "
                            "Optimized Edsv5 Series Compute", sku_name="4 vCore"))
    assert compute.function == "managed_db"
    assert compute.specs == {"engine": "postgresql", "ha": False, "arch": "x86",
                             "purpose": "memory", "burstable": False, "vcpu": 4,
                             "memory_gib": Decimal(32)}
    storage = profile(azure("managed_db", "Azure Database for PostgreSQL", "1 GB/Month",
                            product_name="Azure Database for PostgreSQL Flex Server Storage"))
    assert (storage.function, storage.unit_kind) == ("db_storage", "gb_month")


def test_gcp_machine_core_and_storage():
    core = profile(gcp("vm", "Compute > GCE > VMs On Demand > Cores: Per Core > E2",
                       "E2 Instance Core running in Americas", "h"))
    assert (core.function, core.unit_kind) == ("vm", "hour")
    assert core.specs == {"family": "E2", "arch": "x86", "os": "linux", "burstable": False,
                          "purpose": "general"}
    storage = profile(gcp("object_storage",
                          "Storage > GCS > Storage > Standard > Regional and Dual-Regional",
                          "Standard Storage US Regional", "GiBy.mo"))
    assert (storage.function, storage.unit_kind) == ("object_storage", "gb_month")
    assert storage.specs == {"storage_class": "hot", "redundancy": "zonal"}
    nearline = profile(gcp("object_storage", "Storage > GCS > Storage > Nearline > Multi-Regional",
                           "Nearline Storage US Multi-region", "GiBy.mo"))
    assert nearline.specs == {"storage_class": "cool", "redundancy": "geo"}


def test_gcp_cloud_sql_vcpu():
    p = profile(gcp("managed_db", "Databases > Cloud SQL > Postgres > Compute > vCPU",
                    "Cloud SQL for PostgreSQL: Regional - vCPU in Americas", "h"))
    assert p.function == "managed_db"
    assert p.specs == {"engine": "postgresql", "ha": True, "arch": "x86"}


def test_unknown_things_are_left_out():
    p = profile(aws("AmazonGlue", "AWS Glue", group="ETL Job run"), unit="DPU-Hour")
    assert (p.function, p.unit_kind, p.specs) == ("other", "dpu_hour", {})
    assert profile(aws("AmazonX", "Y"), unit="Widgets").unit_kind == "unknown"
    assert unit_kind(None) == "unknown"


def test_product_labels_are_readable():
    assert product_label(aws("AmazonEC2", "Compute Instance", instanceType="t4g.xlarge",
                             servicename="Amazon Elastic Compute Cloud")) == (
        "Amazon Elastic Compute Cloud · Compute Instance · t4g.xlarge")
    assert product_label(azure("vm", "Virtual Machines", "1 Hour",
                               product_name="Virtual Machines Dsv5 Series",
                               arm_sku_name="Standard_D4s_v5", meter_name="D4s v5")) == (
        "Virtual Machines Dsv5 Series · Standard_D4s_v5 · D4s v5")


# --- Rules found against the real catalog (2026-11-13) ---------------------------------------------


@pytest.mark.parametrize(("arm_sku", "purpose"), [
    ("Standard_DC2ds_v3", "confidential"), ("Standard_E4s_v5", "memory"),
    ("Standard_F4s_v2", "compute"), ("Standard_NC6s_v3", "accelerated"),
])
def test_azure_vm_purpose_from_the_family(arm_sku, purpose):
    p = profile(azure("vm", "Virtual Machines", "1 Hour", arm_sku_name=arm_sku))
    assert p.specs["purpose"] == purpose


def test_confidential_azure_vms_have_no_memory_ratio():
    p = profile(azure("vm", "Virtual Machines", "1 Hour", arm_sku_name="Standard_DC2ds_v3"))
    assert "memory_gib" not in p.specs


@pytest.mark.parametrize(("family", "purpose"), [("N2", "general"), ("A2", "accelerated"),
                                                 ("C3", "compute"), ("M3", "memory")])
def test_gcp_machine_purpose(family, purpose):
    p = profile(gcp("vm", f"Compute > GCE > VMs On Demand > Cores: Per Core > {family}",
                    f"{family} Instance Core running in Americas", "h"))
    assert p.specs["purpose"] == purpose


def test_azure_database_abbreviations():
    p = profile(azure("managed_db", "Azure Database for PostgreSQL", "1 Hour",
                      product_name="Azure Database for PostgreSQL Flex Server Gen Purp Dsv5",
                      sku_name="4 vCore"))
    assert (p.specs["purpose"], p.specs["memory_gib"]) == ("general", Decimal(16))


@pytest.mark.parametrize(("usagetype", "transfer"), [
    ("USE1-USW2-AWS-Out-Bytes", "inter_region"), ("DataTransfer-Out-Bytes", "internet"),
])
def test_aws_transfer_kinds(usagetype, transfer):
    p = profile(aws("AWSDataTransfer", "Data Transfer", usagetype=usagetype))
    assert p.specs["transfer"] == transfer


def test_gcp_and_azure_transfer_kinds():
    inter = profile(gcp("data_transfer", "Network > Egress > GCE > Inter-region",
                        "Network Inter Region Data Transfer Out from Americas to Americas",
                        "GiBy"))
    services = profile(gcp("data_transfer", "Network > Egress > GCE > Google",
                           "Network Data Transfer to Google Services from Delhi", "GiBy"))
    internet = profile(azure("data_transfer", "Bandwidth", "1 GB",
                             product_name="Bandwidth - Routing Preference: Internet",
                             meter_name="Standard Data Transfer Out"))
    assert (inter.specs["transfer"], services.specs["transfer"], internet.specs["transfer"]) == (
        "inter_region", "other", "internet")


def test_dns_visibility_and_load_balancer_types():
    private = profile(azure(None, "Azure DNS", "1M", meter_name="Private Queries"))
    public = profile(azure(None, "Azure DNS", "1M", meter_name="Public Queries"))
    assert (private.specs["visibility"], public.specs["visibility"]) == ("private", "public")
    alb = profile(aws("AWSELB", "Load Balancer-Application", usagetype="LoadBalancerUsage"))
    gateway = profile(azure(None, "Load Balancer", "1 Hour", product_name="Load Balancer",
                            meter_name="Gateway"))
    standard = profile(azure(None, "Load Balancer", "1 Hour", product_name="Load Balancer",
                             meter_name="Standard Included LB Rules and Outbound Rules"))
    appgw = profile(azure(None, "Application Gateway", "1 Hour",
                          product_name="Application Gateway Standard v2",
                          meter_name="Standard Fixed Cost"))
    assert (alb.specs["lb_layer"], gateway.specs["lb_layer"], standard.specs["lb_layer"],
            appgw.specs["lb_layer"]) == ("application", "gateway", "network", "application")


def test_gcp_storage_operations_and_cloud_sql_storage_ha():
    ops = CatalogItem(provider="gcp", service_code="S", service_name="Cloud Storage",
                      product_family="Storage > GCS > Ops", sku="1",
                      summary="Standard Storage Class A Operations", attributes={},
                      unit="count", kind=None)
    assert profile(ops).function == "object_requests_write"
    zonal = profile(gcp("block_storage", "Databases > Cloud SQL > Postgres > Storage",
                        "Cloud SQL for PostgreSQL: Zonal - Standard storage in Americas",
                        "GiBy.mo"))
    assert (zonal.function, zonal.specs["ha"]) == ("db_storage", False)


def test_azure_blob_rows_that_arent_data_stored_are_other():
    p = profile(azure("object_storage", "Storage", "1",
                      product_name="General Block Blob v2", sku_name="Hot LRS",
                      meter_name="Hot LRS Data Retrieval"))
    assert p.function == "other"


@pytest.mark.parametrize(("product", "meter", "function", "edition"), [
    ("Application Gateway Standard v2", "Standard Fixed Cost", "load_balancer", "standard"),
    ("Application Gateway Standard v2", "Standard Capacity Units", "load_balancer_capacity",
     "standard"),
    ("Application Gateway WAF v2", "Standard Fixed Cost", "load_balancer", "waf"),
    ("Application Gateway Basic v2", "Basic Fixed Cost", "load_balancer", "basic"),
    ("Application Gateway Standard v2", "Confidential Compute Fixed Cost", "load_balancer",
     "confidential"),
    # Not an Application Load Balancer equivalent: v1 (being retired), the Kubernetes ingress
    # product, a discounted offer, and WAF captcha sessions.
    ("Basic Application Gateway", "Small Gateway", "other", None),
    ("Application Gateway for Containers", "Standard AGC", "other", None),
    ("Application Gateway WAF v2 - Discounted", "Standard Fixed Cost", "other", None),
    ("Application Gateway WAF v2", "Standard Captcha Sessions", "other", None),
])
def test_application_gateway_v2_editions(product, meter, function, edition):
    got = profile(azure(None, "Application Gateway", "1/Hour", product_name=product,
                        meter_name=meter))
    assert (got.function, got.specs.get("lb_edition")) == (function, edition)


def test_an_application_load_balancer_is_the_standard_edition_and_a_network_one_has_none():
    alb = profile(aws("AWSELB", "Load Balancer-Application", usagetype="LoadBalancerUsage"))
    nlb = profile(aws("AWSELB", "Load Balancer-Network", usagetype="LoadBalancerUsage"))
    assert (alb.specs.get("lb_edition"), nlb.specs.get("lb_edition")) == ("standard", None)


def test_transfer_between_regions_has_its_destination():
    aws_row = profile(aws("AWSDataTransfer", "Data Transfer", usagetype="USE1-USW2-AWS-Out-Bytes",
                          toRegionCode="us-west-2"))
    assert (aws_row.specs["dest_geo"], aws_row.specs["dest_place"]) == ("north_america", "Oregon")
    group = profile(gcp("data_transfer", "Network",
                        "Network Inter Region Data Transfer Out from Virginia to Americas", "GiBy"))
    place = profile(gcp("data_transfer", "Network",
                        "Network Inter Region Data Transfer Out from Virginia to Columbus", "GiBy"))
    assert group.specs.get("dest_geo") == "americas" and "dest_place" not in group.specs
    assert place.specs.get("dest_place") == "Columbus" and "dest_geo" not in place.specs
