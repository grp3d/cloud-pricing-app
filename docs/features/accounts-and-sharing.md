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

Four public architectures owned by Admin are created once, when the database is first set up:

- Active-Standby Multi-Region Web Application
- Modern Data Lake & ETL Analytics Pipeline
- Serverless Microservices Back-End
- Containerized Microservices Platform (EKS)

They're AWS architectures with one VPC per region they use and one priced service per usage
figure; any figure with no matching SKU was left out rather than approximated. Anyone logged in
can import a copy from the Admin group. If the Admin deletes or renames one, it isn't recreated.
How they're generated is in [development.md](../development.md#standard-architectures).

## Specs

[001](../../specs/001-assemble-price-aws-architecture/spec.md) (US3),
[012](../../specs/012-user-accounts-sharing/spec.md) (US2–US4),
[014](../../specs/014-architecture-templates-import-export/spec.md) (US1),
[021](../../specs/021-workspace-layout-redesign/spec.md) (US1, US6: the menu replaced Column 1).
