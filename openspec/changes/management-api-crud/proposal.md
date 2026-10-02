# Management API CRUD

## Why

Huginn has a synchronous Flask management foundation and a fresh operational
schema for Account, User, and ProfessionalProfile, but it does not yet provide
the authenticated workflows needed to manage a user's profile or configure
client discovery. KAN-70 tracks this backend MVP: provision one owner account,
protect each user's data, and let each user maintain offerings, targeting
profiles, and strategies before UI or matching work depends on them.

The identity boundary matters to every later capability. Account owns
credentials and lifecycle; User owns personal/contact data and is the
ownership root; ProfessionalProfile holds professional evidence. These three
records form an aggregate lifecycle: provisioning must create all three
together, and callers must not manipulate Account, User, or Profile as
unrelated generic CRUD resources.

Multi-value ICP targeting also needs an unambiguous contract before matching
can consume it. KAN-76 currently says an empty positive list is unrestricted;
the confirmed MVP decision is that any empty positive list yields no matches.
The ticket and related documentation must be reconciled with that decision.

## What Changes

Deliver the management CRUD slice in dependency order: atomic Account/User/
ProfessionalProfile provisioning; authentication, revocable sessions, and
User ownership enforcement; User and ProfessionalProfile management;
ServiceOffering management; IdealClientProfile (ICP) management; multiple
ClientDiscoveryStrategy management; and end-to-end verification with a local
runbook. The API remains multi-user, with ownership resolved from the
authenticated User. Strategies reference offerings and ICPs belonging to
that same User; more than one strategy may be active at once.

ICP criteria use flat, independent positive lists for industries, company
sizes, and geographies. Values within one dimension combine with OR; the
dimensions combine with AND, so every selected value may combine with every
selected value in the other dimensions. If any positive list is empty,
matching short-circuits to no results. Exclusions are global hard vetoes: a
match against any exclusion rejects the company, and an empty exclusion list
adds no veto. This is not a correlated-segment model and does not materialize
Cartesian combinations. Preference weighting is deferred.

The change preserves the existing synchronous Flask, Pydantic, psycopg, and
handwritten SQL stack. It does not add UI, public registration, matching
execution, BuyerPersona or EngagementPreferences workflows, migration tooling,
or legacy-data backfill. Existing Match identity remains per User/company.

## Capabilities (New/Modified)

### New capabilities

- `identity-aggregate` (`specs/identity-aggregate/spec.md`): Provision
  Account, User, and ProfessionalProfile together and preserve their required
  aggregate lifecycle.
- `authentication-sessions` (`specs/authentication-sessions/spec.md`):
  Authenticate provisioned accounts and enforce revocable sessions and
  owner-scoped access.
- `user-profile-management` (`specs/user-profile-management/spec.md`): Let
  the authenticated User read and update required contact data and the
  associated ProfessionalProfile and validated collections.
- `service-offerings` (`specs/service-offerings/spec.md`): Provide
  owner-scoped lifecycle operations for multiple offerings, preserving
  referential integrity when strategies use them.
- `ideal-client-profiles` (`specs/ideal-client-profiles/spec.md`): Provide
  owner-scoped ICP lifecycle operations with typed multi-value targeting, the
  flat AND/OR rules above, and global exclusion vetoes.
- `discovery-strategies` (`specs/discovery-strategies/spec.md`): Let a User
  manage multiple strategies, including multiple active strategies, each
  referencing that User's offering and ICP.

### Modified capabilities

None. No existing OpenSpec capability specifications are present to modify.

## Impact

This change builds on the existing `huginn.management` Flask application,
Pydantic schemas, psycopg configuration, and `operational` schema. It adds
management persistence and API behavior in the sequence tracked by Jira
KAN-72 through KAN-78, under epic KAN-70. It affects Account/User/Profile,
ServiceOffering, IdealClientProfile, and ClientDiscoveryStrategy contracts;
KAN-18 matching remains a downstream consumer rather than part of this
delivery. End-to-end verification and the local runbook provide delivery
evidence for the capabilities; they are not separate product capabilities.
The new capability paths above establish the specifications for this change.
