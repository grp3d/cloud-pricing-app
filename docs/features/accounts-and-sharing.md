# Accounts and sharing

## Guests and logins

- A new browser starts as a **guest**. A guest can build and price architectures like anyone
  else; they're stored on the server under a random ID kept in that browser, so they're reachable
  only from that browser, and lost to it if its site data is cleared. Guests can't share or
  import. Guest IDs that are no longer used are never cleaned up.
- The person icon in the header shows **Guest** or your username. **Login** (or **Change user**
  once logged in) asks for a username, then:
  - if the account has no password yet, asks you to create one, and logs you in;
  - otherwise asks for the password.
- A username that doesn't exist, a wrong password, or a deactivated account just closes the
  dialog, with no error, and leaves you as you were.
- Usernames are case-sensitive.
- You stay logged in in that browser, across reloads and restarts, until you change user. There's
  no way back to guest yet (short of clearing the browser's site data); an explicit **Log out**
  is planned.
- Accounts are created by the Admin (see [admin](admin.md)). There's one administrator, the
  built-in `Admin` account.

**Logins aren't a security boundary.** The browser identifies itself to the server by the
account's ID, with no session or token check; the password only guards the login dialog. Access
to a deployed instance is controlled by the network allowlist (see
[operations.md](../operations.md#allowlist)), so share an instance only with people you trust
with every account on it.

## Public architectures

- An owner can make their architecture **public** or **private** with the share button in the
  architecture menu. Architectures start private. The button has a green border while public.
- Guests' architectures can't be made public.

## Importing a copy

**Import**, in a provider's panel of the architecture menu, lists that provider's public
architectures owned by other users, grouped by owner: the Admin's group first, then the others
alphabetically, each sorted by name. Choosing one asks for a name, pre-filled with "My <original
name>", and creates a full, independent, private copy with its collections, connectors and
services. Later changes to either don't affect the other. Box positions and other per-browser
layout aren't copied.

## Standard architectures

Each provider (AWS, GCP and Azure) has four public architectures owned by Admin, with the same
names on all three:

- Active-Standby Multi-Region Web Application
- Modern Data Lake & ETL Analytics Pipeline
- Serverless Microservices Back-End
- Containerized Microservices Platform (EKS)

Each has one collection per region it uses (a VPC on AWS and GCP, a VNet on Azure) and one
priced service per usage figure. The GCP and Azure versions are the equivalents of the AWS
designs, with the same sizes and usage figures, so the three totals of a design can be compared:

- **Regions:** the nearest equivalent the pricing data has. us-east-1 → us-east1 / eastus,
  us-west-2 → us-west1 / westus2, eu-west-1 → europe-west1 / westeurope (Azure's Ireland region
  isn't collected).
- **Sizes:** where no size matches exactly, the smallest with at least the same vCPU and memory.
- **Left out:** a figure is matched only when the provider bills the same kind of unit (with at
  most a simple scale); anything else, and anything the AWS version leaves out, is left out
  rather than approximated. So some totals cover less than the AWS one: for example Redshift
  isn't in the GCP or Azure data lake, and the Fargate pods aren't in the Azure EKS platform.
  What was matched and left out, with the reasons, is in each provider's report
  (`backend/src/db/seed/standard_architectures*_report.md`); the app itself doesn't show it.

Anyone logged in can import a copy from the Admin group. Each is created once per database: the
AWS four when the database is first set up, the GCP and Azure eight by the release that added
them (existing databases get them on their next bring-up). If the Admin deletes or renames one,
it isn't recreated. How they're generated is in
[development.md](../development.md#standard-architectures).

## Specs

[001](../../specs/001-assemble-price-aws-architecture/spec.md) (US3),
[012](../../specs/012-user-accounts-sharing/spec.md) (US2–US4),
[014](../../specs/014-architecture-templates-import-export/spec.md) (US1),
[021](../../specs/021-workspace-layout-redesign/spec.md) (US1, US6: the menu replaced Column 1),
[022](../../specs/022-gcp-azure-standard-architectures/spec.md) (GCP and Azure standard architectures).
