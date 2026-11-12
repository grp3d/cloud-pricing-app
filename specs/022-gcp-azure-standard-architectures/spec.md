# Feature Specification: GCP and Azure Standard Architectures

**Feature Branch**: `022-gcp-azure-standard-architectures`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "../speckit-inputs/cloud-pricing-app-gcp-azure-standard-architectures.md": add GCP and Azure equivalents of the four AWS standard architectures (eight new public Admin architectures), created automatically once in every environment, with a report of what was matched and what was left out.

## Overview

The Admin account holds four public standard architectures, all on AWS:

1. Active-Standby Multi-Region Web Application
2. Modern Data Lake & ETL Analytics Pipeline
3. Serverless Microservices Back-End
4. Containerized Microservices Platform (EKS)

GCP and Azure became providers in 019, but neither has a standard architecture. A new user who
picks GCP or Azure starts from a blank canvas, while an AWS user starts from four realistic
examples. This feature adds the GCP and Azure equivalents of each of the four, eight new
architectures in all. They are created automatically in every environment, the same way the AWS
ones are.

Because each equivalent keeps the shape, sizes and usage figures of the AWS original, the same
design can be priced on all three providers and compared like for like. The record of which AWS
component was matched to which GCP and Azure service is also kept in a reusable form, so that
later work (the agent's cross-cloud translation) can start from these matches.

### Equivalent services

| AWS original (region) | GCP equivalent (region) | Azure equivalent (region) |
|---|---|---|
| **Active-Standby Multi-Region Web Application**: Route 53, EC2, Aurora PostgreSQL, S3, load balancer, data transfer (us-east-1 primary, us-west-2 standby) | Cloud DNS, Compute Engine, Cloud SQL for PostgreSQL, Cloud Storage, Cloud Load Balancing, network egress (us-east1, us-west1) | Azure DNS, Virtual Machines, Azure Database for PostgreSQL, Blob Storage, Load Balancer, bandwidth (eastus, westus2) |
| **Modern Data Lake & ETL Analytics Pipeline**: Kinesis, Glue, S3, Athena, Redshift (us-east-1) | Pub/Sub, Dataflow, Cloud Storage, BigQuery on-demand queries, BigQuery storage (us-east1) | Event Hubs, Data Factory, Data Lake Storage, Synapse serverless SQL, Synapse dedicated SQL pool (eastus) |
| **Serverless Microservices Back-End**: Cognito, API Gateway, Lambda, DynamoDB, SQS, SNS (eu-west-1) | Identity Platform, API Gateway, Cloud Run functions, Firestore, Pub/Sub (europe-west1) | Entra External ID, API Management (Consumption), Functions, Cosmos DB, Service Bus, Event Grid (westeurope) |
| **Containerized Microservices Platform (EKS)**: EKS, EC2 nodes, ECR, load balancer, ElastiCache for Redis, RDS for MySQL (us-west-2) | GKE, Compute Engine nodes, Artifact Registry, Cloud Load Balancing, Memorystore for Redis, Cloud SQL for MySQL (us-west1) | AKS, virtual machine nodes, Container Registry, Load Balancer, Azure Cache for Redis, Azure Database for MySQL (westus2) |

- **Database engines** follow the AWS original: PostgreSQL where AWS uses Aurora PostgreSQL,
  MySQL where AWS uses RDS for MySQL.
- **Regions** use the nearest equivalent. GCP has no region in Ireland, so europe-west1
  (Belgium) stands in for eu-west-1. Azure's Ireland region (northeurope) isn't collected by the
  pricing pipeline, so westeurope (Netherlands) stands in for it. Oregon (us-west-2) maps to GCP
  us-west1 and Azure westus2. A region must be one the pricing pipeline collects.
- **Sizes and usage** (vCPU and memory, storage amounts, request counts, hours) match the AWS
  original as closely as each provider's catalog allows. Where AWS runs an instance 24 hours a
  day, the equivalent does too.

## Clarifications

### Session 2026-11-11

- Q: Should the GCP and Azure versions use exactly the services in the equivalents table, or should any change? → A: Keep the table exactly as written (no Traffic Manager on Azure; Dataflow, not Dataproc, on GCP).
- Q: When no GCP or Azure machine size matches the AWS original's vCPU and memory exactly, which size is used? → A: The smallest size with at least the same vCPU and memory; the report shows both sizes.
- Q: How does a user opening a GCP or Azure version learn that components were left out? → A: Only through the repo report. Architecture fields such as the description aren't used to carry this.
- Q: How are AWS figures with no simple counterpart handled (Redshift Serverless RPU-hours; Fargate on Azure)? → A: Left out with a reason. There's no complex logic to force a mapping: a figure is matched only when the counterpart bills the same kind of unit with at most a simple scale. So Redshift is left out on GCP and Azure ("BigQuery storage" and "Synapse dedicated SQL pool" in the table have no AWS figure to size them from), and Fargate is left out on Azure. Fargate on GCP maps to GKE Autopilot pod vCPU and memory hours.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A GCP or Azure user starts from a standard architecture (Priority: P1)

A user filters the architecture list to GCP (or Azure). They see the four public standard
architectures owned by Admin, open one, and it prices when they calculate.

**Why this priority**: This is the reason for the feature. Without it, GCP and Azure users have
no starting point and no realistic example of what the app can price.

**Independent Test**: On a freshly migrated database, each provider (AWS, GCP, Azure) shows
exactly four public Admin architectures, and each of the eight new ones calculates a non-zero
total with every included service priced.

**Acceptance Scenarios**:

1. **Given** a fresh database, **When** it is brought up, **Then** the Admin owns four public
   GCP and four public Azure standard architectures, besides the four AWS ones.
2. **Given** a GCP or Azure standard architecture, **When** it is opened, **Then** each service
   shows its provider icon (020), and calculating prices every service in it.
3. **Given** a GCP machine or an Azure virtual machine in a standard architecture, **When** it is
   opened, **Then** its machine settings (vCPU and memory for GCP, operating system for Azure)
   are filled in, so it prices correctly and Price Change works on it as for any machine the
   user adds.
4. **Given** a user who can import, **When** they open the architecture menu's Import list,
   **Then** the eight new architectures appear under Admin and can be imported like the AWS
   ones.

---

### User Story 2 - They appear in every environment without manual steps (Priority: P1)

The eight architectures reach local development, a brand-new cloud environment and the existing
production environment through the normal bring-up, with nobody creating them by hand.

**Why this priority**: Production already has data. If the architectures only appeared on fresh
databases, existing users would never see them.

**Independent Test**: Bring up an environment restored from a backup taken before this release
and confirm the eight are added once; bring it up again and confirm nothing changes.

**Acceptance Scenarios**:

1. **Given** an existing environment (local development, or production with data), **When** the
   release with this feature is deployed, **Then** the eight architectures are added once and
   the four AWS ones are left exactly as they were.
2. **Given** an Admin who later deletes or renames one of the eight, **When** later releases are
   deployed, **Then** it is not recreated or renamed back ("created once, never recreated", the
   same rule as for AWS).
3. **Given** a brand-new environment with no backup, **When** it is brought up, **Then** all
   twelve standard architectures exist.
4. **Given** an environment restored from a backup taken before this release, **When** it is
   brought up, **Then** the eight are added once.

---

### User Story 3 - It's clear what was matched and what was left out (Priority: P2)

Generating the architectures produces a report, like the AWS one, listing for each architecture
every matched service and SKU with its quantity, and every component or figure that has no
equivalent in the pricing data, with the reason.

**Why this priority**: The owner needs to check the equivalents are sensible, and users need
honest totals. A guessed substitute would produce confident but misleading figures.

**Independent Test**: Read the report and confirm every component of every AWS original appears
in it for both GCP and Azure, either as matched or as left out with a reason.

**Acceptance Scenarios**:

1. **Given** a component with no match in the GCP or Azure pricing data (for example Entra
   External ID or Event Grid), **When** the architectures are generated, **Then** it is left out
   of the architecture and listed in the report with the reason. It is never replaced with a
   guess.
2. **Given** the same pricing snapshot and the same reference, **When** generation is run again,
   **Then** the output is identical.
3. **Given** the report, **When** it is read, **Then** each matched entry names the AWS component
   it stands in for, so the AWS-to-GCP and AWS-to-Azure correspondence can be reused later.

---

### User Story 4 - A user compares a design across the providers (Priority: P2)

A user opens the AWS, GCP and Azure versions of one design and calculates each at the same
duration to see which provider costs less for that design.

**Why this priority**: Like-for-like comparison is the second benefit of the feature, but it
follows from Stories 1 and 3 without extra work.

**Independent Test**: For one design, calculate all three versions at the 1-month duration and
confirm they share the same name, the same collections in the same order, and the same usage
figures wherever a matching service exists.

**Acceptance Scenarios**:

1. **Given** the three versions of one design, **When** each is calculated at the same duration,
   **Then** the totals can be compared directly: same name, same shape, same usage figures.

---

### Edge Cases

- **Name clashes**: the Admin already owns a non-deleted architecture with the same name *and*
  provider. It is skipped, not duplicated. The AWS originals share names with the new ones, so
  the check must include the provider.
- **No GCP or Azure pricing data yet**: the architectures are still created, because they hold
  SKU references, not prices. They price once the data arrives.
- **A SKU disappears from a later pricing snapshot**: handled the same way as for the AWS
  architectures today; nothing new.
- **No default Admin**: an environment where the default Admin account doesn't exist. Nothing is
  created, as for the AWS architectures, and bring-up still succeeds.
- **A partly applied earlier attempt**: some of the eight already exist (for example after a
  manual fix). Only the missing ones are created.
- **Test data**: the backend and end-to-end tests run on a small pricing data set, which must
  include every SKU the eight architectures use.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide eight new public standard architectures owned by the
  default Admin: the GCP and the Azure equivalent of each of the four AWS standard architectures,
  using the services and regions in the Equivalent services table.
- **FR-002**: Each new architecture MUST have the same name as its AWS original, and the same
  collections in the same order, with each collection's region changed to the equivalent region.
- **FR-003**: Each included service MUST reference a SKU that exists in that provider's pricing
  data, with sizes and usage figures matching the AWS original as closely as the catalog allows.
  Where no machine (or managed database or cache node) size matches the original's vCPU and
  memory exactly, the smallest size with at least the same vCPU and memory MUST be used, and the
  report MUST show both the original and the chosen size.
- **FR-004**: GCP machines MUST carry their vCPU and memory settings, and Azure virtual machines
  their operating system, so that they price correctly and Price Change applies to them.
- **FR-005**: A component or figure with no equivalent in the provider's pricing data MUST be
  left out and recorded in the report with the reason. The system MUST NOT substitute a guessed
  service.
- **FR-006**: Left-out components MUST be recorded only in the report. The architectures' own
  fields (name, description, collection names) MUST NOT be used to carry this information.
- **FR-007**: The eight MUST be created automatically during an environment's normal bring-up,
  with no manual step, in fresh, existing and restored environments alike.
- **FR-008**: Each of the eight MUST be created at most once per database. It MUST be skipped if
  the Admin already owns a non-deleted architecture with the same name and provider, and it MUST
  NOT be recreated or changed after the Admin deletes or renames it.
- **FR-009**: The four AWS standard architectures MUST NOT change.
- **FR-010**: The architectures and the report MUST be generated from a reference description of
  the designs and the real pricing data, never written or edited by hand, and generation MUST be
  repeatable: the same inputs give identical output.
- **FR-011**: The report MUST list, per architecture, each matched component with the AWS
  component it stands in for, its service, SKU, unit and quantity, and each left-out component
  or figure with its reason.
- **FR-012**: The test pricing data set MUST include every SKU used by the eight architectures,
  and automated tests MUST confirm that every included service resolves to a price.
- **FR-013**: The feature MUST update the matching page in `docs/features/` and add a line to
  `CHANGELOG.md` under the release it ships in.

### Key Entities

- **Standard architecture**: a public architecture owned by the default Admin, with a name, a
  provider, a description, collections (each with a region) and services. Identified for
  creation purposes by its name together with its provider.
- **Reference design**: the provider-neutral description of one of the four designs (its
  components, sizes and usage figures), from which each provider's version is generated.
- **Component match**: one AWS component's counterpart on GCP or Azure: the service, SKU, unit
  and quantity chosen, or "left out" with a reason. The collection of matches is the report, and
  the seed for later cross-cloud mappings.
- **Machine settings**: the provider-specific settings a machine needs to be priced (vCPU and
  memory for GCP, operating system for Azure).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh database, each of the three providers shows exactly four public Admin
  standard architectures (twelve in all).
- **SC-002**: Each of the eight new architectures calculates a non-zero total, and 100% of their
  included services are priced.
- **SC-003**: Bringing up an environment restored from a pre-release backup adds exactly eight
  architectures; bringing it up again adds none.
- **SC-004**: 100% of the AWS originals' components appear in the report for both GCP and Azure,
  either matched or left out with a reason.
- **SC-005**: Running generation twice on the same inputs produces byte-identical output.
- **SC-006**: The four AWS standard architectures are unchanged after the release (same names,
  collections, services and usage figures).
- **SC-007**: A GCP or Azure user can open a standard architecture and see its priced total in
  under a minute from first loading the app.

## Assumptions

- **Names** are identical to the AWS originals, with no provider suffix, because the
  architecture list is already grouped by provider. The equivalent-services table above is
  final (confirmed in clarification).
- **DNS only** on Azure and GCP, with no global traffic manager, matching the AWS original,
  which uses Route 53 DNS queries only (its hosted zones and health checks have no prices in the
  data).
- **Unpriceable components are left out and reported**, as for AWS, rather than added unpriced.
- **No connectors or nested collections**: the AWS originals have none, so neither do the
  equivalents.
- **Creation is once per database**, as for AWS. No reset or restore command is offered.
- **The default Admin account** is the owner, as for AWS.
- **Pricing data** for GCP and Azure is available to whoever generates the architectures; an
  environment without it still receives the architectures.
- **Release**: ships as a pre-1.0 release (v0.1.x or v0.2.0, the owner's choice).
- **Later use**: agent-04 (cross-cloud translation) will seed its first reviewed AWS-to-GCP and
  AWS-to-Azure service mappings from this feature's component matches. Building those mappings,
  and any review queue, is not part of this feature.

## Out of Scope

- A button or command to reset or restore the standard architectures.
- Connectors (arrows) or nested collections inside the standard architectures.
- A cross-cloud Compare tab, and the agent's service-mapping data and its Admin review queue.
- Changing the four AWS standard architectures.
- GCP or Azure versions of designs other than the four.
