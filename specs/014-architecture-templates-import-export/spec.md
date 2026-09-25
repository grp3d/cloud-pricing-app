# Feature Specification: Standard Architectures and Admin Architecture Import/Export

**Feature Branch**: `014-architecture-templates-import-export`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "see docs/functionality_2026-09-25.md". The source document covers two related capabilities: (1) seeding four standardized, shareable "common architecture" standard architectures (Active-Standby Multi-Region Web Application; Modern Data Lake & ETL Analytics Pipeline; Serverless Microservices Back-End; Containerized Microservices Platform (EKS)) owned by the Admin account and persisted so they are immediately available, with each component matched to a service in the pricing dataset (first match wins, no prompting), placed in one VPC per listed region, and no application-component collections; and (2) a new admin-only ability, on the Admin tab, to export a user's architectures to a JSON file on the admin's own computer and import architectures from such a file into a user's account, via two new word-wrapped columns ("Import Architectures from Disk", "Export Architectures to Disk") placed between the Password and Purge columns, with per-architecture partial success and a post-import status popup. The import/export file uses its own format capable of fully recreating architectures as they are stored today. The baseline JSON embedded in the source document was later replaced by `docs/common_aws_architectures.md` (version 1.1), which is the only source for the standard architectures' contents (see Clarifications).

## Clarifications

### Session 2026-09-25

- Q: The Export button is per user row, but the proposed filename named a single architecture. What does one Export click produce? → A: One file containing all of that user's architectures, named `username_<timestamp>.json`.
- Q: Should `docs/common_aws_architectures.md` be the only source for the four standard architectures, with the small inconsistencies against the written descriptions settled as the JSON has them? → A: Yes. The JSON is the only source, as written: EKS RDS MySQL uses gp3 storage at 3,000 IOPS; the serverless back-end has SQS at 10M requests plus SNS at 2M publishes; the EKS platform has 6 EC2 m6i.large nodes plus 10 Fargate pods. JSON service names are translated to the names the pricing data uses (e.g., ElasticLoadBalancing → AWSELB, AmazonAPIGateway → AmazonApiGateway, AmazonSQS → AWSQueueService, AWSFargate → EKS Fargate compute under AmazonEKS). AWS App Mesh has no records in the pricing data, so it is left out and logged. The JSON is reference data for building the standard architectures and is not itself loaded into the application.
- Q: When a component in the JSON lists several usage figures, should each become its own priced service entry, or only the component's main cost? → A: Each usage figure with a matching SKU becomes its own service entry. Derived amounts are calculated from the JSON's numbers (e.g., Lambda compute: 15M × 0.25 s × 1 GB = 3.75M GB-seconds).
- Q: If the Admin deletes or renames one of the standard architectures, should the system recreate it the next time it starts? → A: No. They are created once only, and deleting or renaming one is permanent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every user can start from a standard architecture (Priority: P1)

When the application is started, four ready-made architectures already exist under the Admin account: "Active-Standby Multi-Region Web Application", "Modern Data Lake & ETL Analytics Pipeline", "Serverless Microservices Back-End", and "Containerized Microservices Platform (EKS)". Each is built from real services in the pricing dataset that match the components defined for it in `docs/common_aws_architectures.md`, with that file's quantities pre-filled. Each architecture has one VPC per region it lists (the multi-region web application has a us-east-1 VPC and a us-west-2 VPC), and each component sits inside the VPC for its region. The standard architectures are public, so any logged-in user sees them under the Admin group in the existing Import list and can copy one into their own account as a starting point.

**Why this priority**: This is the main user-facing value of the feature: a new user gets a realistic, priced starting point instead of an empty canvas. It works on its own, without the import/export files.

**Independent Test**: On a freshly initialized system, log in as a non-admin user, open the Import list, confirm all four standard architectures appear under the Admin group, import one, and confirm the copy shows the expected VPCs per region, each holding priced services that match its definition in `docs/common_aws_architectures.md`.

**Acceptance Scenarios**:

1. **Given** a freshly initialized system, **When** the Admin logs in, **Then** the four standard architectures appear in the Admin's architecture list with no manual setup step.
2. **Given** the standard architectures exist, **When** any other logged-in user opens the Import list, **Then** all four appear in the Admin group.
3. **Given** the "Active-Standby Multi-Region Web Application" standard architecture, **When** it is opened, **Then** it contains exactly two VPCs, one for us-east-1 and one for us-west-2, and each component sits in the VPC for its region.
4. **Given** any single-region standard architecture (e.g., "Serverless Microservices Back-End" in eu-west-1), **When** it is opened, **Then** it contains exactly one VPC for that region holding all of its components, and no application-component collections.
5. **Given** a component defined with a quantity (e.g., 4× t4g.xlarge compute instances, 2 TB of standard object storage), **When** its standard architecture is opened, **Then** the matching service entry carries that quantity as its usage input, converted to the app's daily-rate convention, and shows a price from the pricing dataset.
8. **Given** a component with several usage figures (e.g., the primary S3 bucket's storage, PUT requests and GET requests), **When** its standard architecture is opened, **Then** each figure with a matching SKU appears as its own priced service entry in that VPC.
6. **Given** a component that could match several services in the pricing dataset, **When** the standard architecture is created, **Then** the first available match is used and nobody is prompted to choose.
7. **Given** the standard architectures were already created, **When** the system restarts, **Then** no duplicate standard architectures are created.

---

### User Story 2 - Admin exports a user's architectures to a file on their computer (Priority: P2)

On the Admin tab, the user table has two new columns between "Password" and "Purge": "Import Architectures from Disk" and "Export Architectures to Disk". Their header text wraps onto more than one line to save width. Each user row has an "Export" button in the export column. Clicking it downloads a JSON file to the admin's own computer through the browser's normal download. The single file contains all of that user's architectures and is named `username_<timestamp-of-download>.json`. It holds everything needed to recreate each architecture exactly as it is stored today, including VPCs, application components, nesting, connectors, service selections, and their pricing inputs.

**Why this priority**: Export is how architectures get moved or backed up between environments or users. It also produces the file that User Story 3 reads, so it comes before import.

**Independent Test**: As the Admin, on the Admin tab, confirm the two new columns sit between Password and Purge with wrapped headers. Click Export on a user who owns architectures, confirm a single correctly named JSON file lands in the browser's download location, and confirm it describes every one of that user's architectures completely.

**Acceptance Scenarios**:

1. **Given** the Admin is on the Admin tab, **When** they view the user table, **Then** "Import Architectures from Disk" and "Export Architectures to Disk" appear, in that order, after "Password" and before "Purge", with header text wrapped onto multiple lines.
2. **Given** a user row, **When** the Admin views it, **Then** it shows an "Import" button in the import column and an "Export" button in the export column.
3. **Given** a user "jdoe" who owns architectures "Web App" and "Data Lake", **When** the Admin clicks Export on jdoe's row, **Then** one file named in the form `jdoe_<timestamp>.json` is saved to the Admin's local computer, not to the server, and it contains both architectures.
4. **Given** an exported file, **When** it is imported back into any user who has no architecture with that name, **Then** the resulting architecture has the same VPCs, application components, nesting, connectors, service selections, regions, and pricing inputs as the original.
5. **Given** an architecture that its owner removed earlier, **When** the Admin exports that user, **Then** the removed architecture is not included.

---

### User Story 3 - Admin imports architectures from a file into a user's account (Priority: P2)

Clicking a user row's "Import" button opens the admin's own file picker. The admin chooses a JSON file on their computer that was produced by this feature's export. If the file as a whole is unreadable or not in the expected format, the admin is told that the import failed and nothing is imported. Otherwise, each architecture in the file is imported into that row's user independently. An architecture that cannot be imported (for example, it references a service that is not in the current pricing dataset, or the user already has an architecture with that name) is skipped, and the rest are still imported. When the import finishes, a popup shows a table with one row per architecture in the file and three columns: status (a green checkmark for success, a red X for failure), architecture name, and error message (a brief reason, filled only for failures).

**Why this priority**: Import completes the round trip that export starts. It depends on the file format from User Story 2 for its test input.

**Independent Test**: Prepare an exported file with three architectures, where one references a service missing from the pricing dataset and one has a name the target user already uses. Import it on that user's row and confirm the popup shows one green checkmark and two red X rows with brief reasons, and that only the one valid architecture was added to the user's account.

**Acceptance Scenarios**:

1. **Given** the Admin clicks "Import" on a user's row, **When** the file picker opens, **Then** it browses the Admin's local computer, not the server.
2. **Given** a selected file that is not valid JSON or does not match the export format as a whole, **When** the import runs, **Then** the Admin is told the import failed and no architectures are added.
3. **Given** a valid file containing architectures A, B, and C, where B has the same name as one of the target user's existing architectures, **When** the import runs, **Then** A and C are added to the target user and B is not.
4. **Given** a valid file containing an architecture that references a service or SKU not present in the current pricing dataset, **When** the import runs, **Then** that architecture is not added and the others are.
5. **Given** an import has finished, **When** the status popup appears, **Then** it lists every architecture in the file with a green checkmark and an empty error message for successes, and a red X with a brief reason (e.g., "Architecture name already exists", "Service not found in pricing data: AmazonXYZ") for failures.
6. **Given** an architecture failed validation partway through, **When** the import finishes, **Then** nothing of that architecture remains in the target user's account (no half-imported architecture).
7. **Given** a non-admin user or a guest, **When** they use the application, **Then** the import/export columns and buttons are not available to them anywhere, and this import is separate from the existing "Import" action on the Cloud Pricing tab.

---

### Edge Cases

- **Standard architectures across restarts**: Standard architectures are created only once. If the Admin deletes or renames one, it is not recreated on the next restart. Restarting a system that already has them never creates duplicates.
- **No pricing-data match for a standard-architecture component**: The component is left out of that standard architecture rather than approximated. The rest of the standard architecture is still created. Which components were left out is recorded where an operator can see it (e.g., the system's startup/seed output).
- **Global components** (e.g., DNS, CDN) listed with region "global": they go into the VPC of the standard architecture's first listed region.
- **Architecture count in a file**: A file containing zero architectures is treated as a valid but empty import. The status popup says that no architectures were found.
- **Duplicate names in one file**: The first is imported. Later ones with the same name fail with "Architecture name already exists".
- **User with no architectures**: The Export button is disabled for that row, so an empty or meaningless file is never downloaded.
- **Import into the Admin**: The Admin's own row supports import and export like any other user's.
- **Visibility after import**: Imported architectures are private in the target account, whatever visibility they had when exported.
- **Pricing data refreshed after export**: An exported service entry whose SKU no longer exists in the current pricing dataset fails that architecture's import with a "not found in pricing data" reason.
- **Large or wrong-type file**: A non-JSON file, or a JSON file of a different shape (e.g., the baseline JSON in the source document or `docs/common_aws_architectures.md`), is rejected as a whole-file failure.
- **Browser cancel**: If the Admin closes the file picker without choosing a file, nothing happens and no popup is shown.

## Requirements *(mandatory)*

### Functional Requirements

**Standard architectures**

- **FR-001**: System MUST provide four standard architectures owned by the default Admin account, named exactly: "Active-Standby Multi-Region Web Application", "Modern Data Lake & ETL Analytics Pipeline", "Serverless Microservices Back-End", and "Containerized Microservices Platform (EKS)".
- **FR-002**: System MUST make these architectures available immediately on system initialization, with no manual setup, including on systems that were already initialized before this feature (created once, on their first start after the upgrade), and MUST store them in the same way as any other user-owned architecture.
- **FR-003**: System MUST create the standard architectures at most once per system. Restarts MUST NOT create duplicates, and standard architectures the Admin later deletes or renames MUST NOT be recreated automatically.
- **FR-004**: System MUST mark the standard architectures as public, so every logged-in user can find them in the Admin group of the existing Import list.
- **FR-005**: System MUST create exactly one VPC collection per region an architecture lists: us-east-1 and us-west-2 for the multi-region web application, us-east-1 for the data lake, eu-west-1 for the serverless back-end, and us-west-2 for the EKS platform.
- **FR-006**: System MUST place each standard architecture component in the VPC for its region. Components whose region is "global" MUST go in the VPC of the architecture's first listed region.
- **FR-007**: System MUST NOT create application-component collections or connectors in the standard architectures.
- **FR-008**: System MUST build the standard architectures only from the components defined in `docs/common_aws_architectures.md` (version 1.1). It MUST match each component to a service and SKU in the current pricing dataset using the component's attributes (service, region, instance/node type, engine, storage class, deployment option, etc.). JSON service names MUST be translated to the pricing dataset's names where they differ (ElasticLoadBalancing → AWSELB, AmazonAPIGateway → AmazonApiGateway, AmazonSQS → AWSQueueService, AWSFargate → EKS Fargate compute under AmazonEKS). When several SKUs match, it MUST use the first available match without prompting anyone.
- **FR-009**: System MUST create one service entry for each usage figure of a component that has a matching SKU (e.g., S3 storage, PUT requests, and GET requests as three entries; Fargate vCPU and memory as two; an RDS instance and its storage as two). Each entry's usage input MUST come from that component's `attributes` and `usage` values in the JSON. Where the SKU's billing unit differs from the JSON's figure, the input MUST be calculated from the JSON's numbers (e.g., Lambda GB-seconds = executions × average duration × memory; Kinesis shard-hours = shards × hours; instance-hours = count × hours). The input MUST be converted to the app's existing daily-rate convention (see Assumptions).
- **FR-009a**: System MUST leave out and log any individual usage figure with no matching SKU, while still creating the component's other entries.
- **FR-010**: System MUST leave out, and not approximate, any standard architecture component for which no matching service exists in the pricing dataset. It MUST record which components were left out so an operator can review them. AWS App Mesh is known to have no pricing records and is expected to be left out.

**Admin import/export controls**

- **FR-011**: System MUST add two columns to the Admin tab's user table, "Import Architectures from Disk" and "Export Architectures to Disk", in that order, directly after "Password" and directly before "Purge". The header text MUST wrap onto multiple lines to limit column width.
- **FR-012**: System MUST show an "Import" button in each user row's import column and an "Export" button in each user row's export column. The Export button MUST be disabled for a user who owns no architectures.
- **FR-013**: System MUST name each exported file `<username>_<timestamp-of-download>.json`. Characters in the username that are not allowed in common desktop filenames MUST be replaced with a safe substitute.
- **FR-014**: System MUST deliver exported files to the admin's local computer through the browser's download mechanism, and MUST NOT write export files to the server's filesystem.
- **FR-015**: System MUST produce exports in a versioned JSON format of its own that holds everything needed to recreate an architecture as stored today: architecture name and provider; every collection with its type, name, region, and parent/child nesting; every connector and its endpoints; and every service selection with its service, SKU, pricing term, purchase option, and usage quantity.
- **FR-016**: System MUST include only the user's current (not removed) architectures in an export, and MUST NOT include passwords, internal identifiers of other users, or any vendor price values.
- **FR-017**: System MUST export all of the selected user's current architectures into a single file per Export click.

**Admin import**

- **FR-018**: System MUST let the admin choose an import file from their local computer through the browser's file picker, and MUST import its architectures into the user whose row's Import button was used.
- **FR-019**: System MUST reject the whole file, add no architectures, and tell the admin that the import failed when the file is not valid JSON, is not in the export format, or declares a format version the system does not support.
- **FR-020**: System MUST validate and import each architecture in a valid file independently. An architecture that fails validation MUST be skipped entirely, without leaving partial data behind, and the others MUST still be imported.
- **FR-021**: System MUST fail an individual architecture's import when, at minimum: the target user already owns a non-removed architecture with the same name (including one imported earlier from the same file); any referenced service or SKU does not exist in the current pricing dataset; any referenced region is not available in the pricing dataset; or the architecture's internal structure is inconsistent (e.g., a connector or nesting reference to a collection that isn't in the architecture).
- **FR-022**: System MUST, after a non-rejected import, show the admin a popup containing a table with one row per architecture in the file and three columns: status (green checkmark for success, red X for failure), architecture name, and error message (a brief failure reason, empty for successes).
- **FR-023**: System MUST make every imported architecture private and owned by the target user, regardless of its visibility or owner in the source system.
- **FR-024**: System MUST keep this Admin-tab import/export entirely separate from the existing Import action on the Cloud Pricing tab. Neither may change the other's behavior.
- **FR-025**: System MUST restrict import/export to the administrator. The columns, buttons, and underlying operations MUST be unavailable to non-admin users and guests.

### Key Entities

- **Standard Architecture**: An ordinary Architecture owned by the default Admin and public from creation. It holds one VPC collection per listed region and, in those VPCs, service selections matched from the pricing dataset with pre-filled quantities. It is not a new kind of object, only a seeded instance of the existing Architecture.
- **Standard Architecture Seed Record**: A marker that the standard architectures were already created for this system, so they are never duplicated or silently recreated.
- **Architecture Export File**: A versioned JSON document produced and consumed only by the Admin-tab import/export. It holds one or more architecture definitions with their full collection, nesting, connector, and service-selection data. It references pricing-dataset services by their stable service and SKU identifiers only, never by copied price values.
- **Import Result**: The outcome for one architecture in an import file: status (success/failure), architecture name, and a brief error message on failure. Import Results are shown to the admin in the post-import popup and are not stored.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a freshly initialized system, all four standard architectures are available to every logged-in user with zero manual setup steps.
- **SC-002**: A user can go from an empty account to a fully priced copy of any standard architecture in under 1 minute.
- **SC-003**: 100% of standard-architecture usage figures that have a matching SKU in the pricing dataset appear in the standard architecture with a price shown. Figures and components without a match are listed for operator review.
- **SC-004**: An architecture exported and then imported into another user is identical to the original in structure, regions, services, and pricing inputs in 100% of round-trip tests where the pricing dataset is unchanged.
- **SC-005**: An admin can export all of a user's architectures or import a file in 3 clicks or fewer from the Admin tab, not counting choosing a file in the file picker.
- **SC-006**: In an import file containing any mix of valid and invalid architectures, 100% of valid architectures are imported, 0% of invalid ones leave any data behind, and every architecture appears in the status popup with the correct status.
- **SC-007**: Zero non-admin identities, including guests, can reach the import/export controls or operations.
- **SC-008**: Adding the two new columns does not cause the Admin user table to scroll horizontally at the widths it fits in today.

## Assumptions

- **Known description text error**: Both source documents call t4g instances "Graviton3". They are actually Graviton2. This has no pricing effect, because matching uses the instance type t4g.xlarge.
- **Daily-rate conversion**: The app treats a service entry's usage quantity as a steady daily rate and scales it by the chosen period (1 day, 1 month = 31 days, 1 year = 365 days). Monthly JSON figures are converted to that daily rate. Always-on resources (730 hrs/month in the JSON) become 24 hours per day per unit, so the app's 1-month view shows 744 hours rather than 730. Per-month counts (requests, messages, GB scanned) are divided by 31. Stored-GB figures billed per GB-month are entered as the stored amount without conversion.
- **Standard architectures are ordinary architectures**: Users "build off" a standard architecture by copying it through the existing Import list (feature 012). This feature adds no separate standard architecture picker. The Admin can edit their standard architectures like any other architecture, and the copies are unaffected.
- **Pricing terms for standard architectures**: Their service selections use on-demand pricing unless the JSON names another purchase option.
- **Where standard architectures are created**: Creation happens in the same initialization step that seeds the default Admin account today, so it needs the pricing dataset to be available at that point.
- **Import target**: A file's architectures go to the user whose row's Import button was clicked, regardless of which user they were exported from.
- **Timestamp in filenames**: The download timestamp uses a sortable, filename-safe format to the second (e.g., `20260925T143022`).
- **Import scope**: Import accepts only files in this feature's export format. Neither the baseline JSON in the source document nor `docs/common_aws_architectures.md` is an accepted import format.
- **Error message style**: Failure reasons in the status popup are one short sentence naming the specific cause (e.g., the missing service code or the conflicting name). They are not technical traces.
- **Provider**: Exported files record the architecture's provider (AWS today), so later providers can be added without changing the format's structure.
