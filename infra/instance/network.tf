# One public subnet, no NAT, no load balancer (FR-040). Inbound: 443 from the allowlist only
# (FR-035); there is no SSH rule at all — the shell is Session Manager (FR-039).

data "aws_ssm_parameter" "allowlist" {
  name = local.base.allowlist_parameter
}

locals {
  # A StringList; "none" is the base stack's placeholder for an empty list (research.md R12).
  allowlist = toset([
    for entry in split(",", data.aws_ssm_parameter.allowlist.insecure_value) :
    trimspace(entry) if trimspace(entry) != "none" && trimspace(entry) != ""
  ])
}

resource "aws_vpc" "app" {
  cidr_block           = "10.40.0.0/24"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${local.prefix}-${local.env}" }
}

resource "aws_internet_gateway" "app" {
  vpc_id = aws_vpc.app.id
  tags   = { Name = "${local.prefix}-${local.env}" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.app.id
  cidr_block              = "10.40.0.0/25"
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.prefix}-${local.env}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.app.id
  tags   = { Name = "${local.prefix}-${local.env}-public" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.app.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "app" {
  name        = "${local.prefix}-${local.env}"
  description = "cloud-pricing-app ${local.env}: HTTPS from the allowlist only"
  vpc_id      = aws_vpc.app.id
  tags        = { Name = "${local.prefix}-${local.env}" }
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  for_each          = local.allowlist
  security_group_id = aws_security_group.app.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = strcontains(each.value, ":") ? null : each.value
  cidr_ipv6         = strcontains(each.value, ":") ? each.value : null
  description       = "allowlist"
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "image pulls, S3, SSM, SNS, logs, apt"
}
