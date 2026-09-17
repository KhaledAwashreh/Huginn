# Account, User, and Client Discovery Domain

Date: 2026-09-16
Last updated: 2026-09-17
Status: In progress

This note records decisions from the account, user, and client-discovery
domain design session. It is not a complete implementation specification.
Confirmed decisions and unresolved questions are kept separate so that open
ideas are not treated as settled architecture.

## Confirmed decisions

### Account

`Account` is the authentication and account-lifecycle entity. It remains
deliberately small and does not own personal, professional, targeting, or
service-delivery information.

Initial fields:

- `id`: UUID
- `username`
- `password_hash`
- `status`
- `created_at`: timezone-aware timestamp
- `updated_at`: timezone-aware timestamp

Accounts are provisioned by the system owner in the initial phase. Public
registration is out of scope.

### User

`User` represents the person and their mandatory personal/contact
information. It replaces the earlier `PersonalProfile` name and is the
ownership root for the person's business-domain entities.

Initial fields:

- `id`: UUID
- `account_id`: unique foreign key to `Account`
- `first_name`
- `last_name`
- `email`
- `phone_number`
- `country_of_residence`
- `timezone`: optional and not yet finally decided
- `created_at`: timezone-aware timestamp
- `updated_at`: timezone-aware timestamp

First name, last name, email, phone number, and country of residence are
mandatory. Country means current country of residence, not country of origin.
The concrete representation of country is not yet decided.

Each Account has exactly one User, and each User belongs to exactly one
Account:

```text
Account 1 --> 1 User
```

Account and User are created atomically during provisioning.

### Professional profile

Each User has exactly one `ProfessionalProfile`. An empty ProfessionalProfile
is created atomically with Account and User, then completed later through
manual onboarding.

Confirmed initial fields:

- `id`: UUID
- `user_id`: unique foreign key to `User`
- `headline`: optional
- `professional_summary`: optional
- `skills`: structured JSON collection
- `experience`: structured JSON collection
- `previous_projects`: structured JSON collection, optional for the user
- `created_at`: timezone-aware timestamp
- `updated_at`: timezone-aware timestamp

Phase 1 onboarding is manual. Resume parsing and ATS-style resume ingestion
are deferred. The ProfessionalProfile must not become a candidate or talent
management model.

The ideal long-term model separates skills, experience, previous projects,
and other repeatable professional information into normalized entities and
tables. The initial implementation deliberately keeps them in the single
ProfessionalProfile entity to minimize phase 1 scope. Collections must still
contain structured objects rather than plain text values.

This is an accepted transitional design. A future migration may extract the
structured collections into normalized child tables once querying,
relationships, provenance, or independent updates justify the additional
model complexity. The object schemas and migration boundary must be defined
before implementation; choosing one table does not permit arbitrary,
unvalidated JSON.

Education, certifications, languages, and other professional-evidence
collections are out of scope for phase 1. They should be added only when a
concrete client-discovery use case requires them.

The phase 1 skill object captures only the skill name:

```text
Skill
- name
```

Skill proficiency, ranking, and years of experience are not captured or
compared in phase 1. Skills are descriptive profile data at this stage, not a
scored matching input.

Experience and previous projects remain distinct. Experience describes the
user's broader professional context. A previous project records concrete work
the user delivered and may later support a service offering or outreach
claim. Previous projects are optional during onboarding and are represented
by an empty collection when omitted, not database `NULL`.

### Client-discovery entities

The following are separate, first-class domain entities. They are not fields
or embedded sections of Account, User, or ProfessionalProfile:

- `ServiceOffering`: what the user can sell to a client.
- `IdealClientProfile`: which organizations the user wants to target.
- `BuyerPersona`: which people within target organizations buy, influence,
  or use the offered service.
- `EngagementPreferences`: commercial and practical engagement constraints.
- `ClientDiscoveryStrategy`: coordinates the entities for a specific client-
  discovery objective.

Each entity is directly owned by User through `user_id`. Domain entities do
not use Account as their ownership key.

ClientDiscoveryStrategy references the applicable entities rather than
copying or absorbing their data. This allows offerings, ideal-client
profiles, buyer personas, and engagement preferences to be reused.

Multiple ClientDiscoveryStrategy records may be active for one User at the
same time. Each MVP strategy references one offering and one ICP owned by
that User. The current conceptual direction is:

```text
Account 1 --> 1 User
                  |
                  +--> 1 ProfessionalProfile
                  +--> many ServiceOffering
                  +--> many IdealClientProfile
                  +--> many BuyerPersona
                  +--> EngagementPreferences
                  +--> many ClientDiscoveryStrategy
```

### Ideal client profile input

Phase 1 ICP input is entered manually by the user as client-targeting
preferences. The user retains control of the targeting criteria.

The following dimensions support multiple selections within one ICP:

- `industries`: list of target industries.
- `company_sizes`: list of company-size bands.
- `geographies`: list of target countries or regions.
- `exclusions`: list of exclusion criteria.

These are collections, not single-answer fields. Exact item schemas,
storage, empty-list behavior, and how criteria combine remain to be defined.
The contract must distinguish preferences from mandatory requirements;
the representation and matching behavior of that distinction remain open.

## Terminology decisions

- Use `Account`, not `User`, for authentication credentials and lifecycle.
- Use `User`, not `PersonalProfile`, for personal/contact information.
- Use `ProfessionalProfile` for the user's professional summary and
  structured professional evidence.
- Use `ServiceOffering`, `IdealClientProfile`, `BuyerPersona`,
  `EngagementPreferences`, and `ClientDiscoveryStrategy` as distinct domain
  concepts.
- Do not use one generic preferences table or an unstructured preferences
  JSON object to represent these concepts.

## Open questions

- Final Account status values and lifecycle transitions.
- Username normalization and uniqueness rules.
- Email and phone normalization and uniqueness rules.
- Whether timezone is required and where it belongs.
- Country representation and validation.
- ProfessionalProfile completion or onboarding state.
- The object schemas for ProfessionalProfile experience and previous-project
  collections.
- The threshold for migrating ProfessionalProfile collections into
  normalized child tables.
- ServiceOffering fields and cardinality.
- IdealClientProfile fields, filters, exclusions, and versioning.
- BuyerPersona fields and its relationship to IdealClientProfile and
  ClientDiscoveryStrategy.
- EngagementPreferences fields and whether preferences are global or vary by
  strategy.
- ClientDiscoveryStrategy fields, lifecycle, cardinalities, and activation
  rules.
- How company signals and matching criteria attach to a strategy.
- How changes to a strategy affect existing matches and explanations.

## Management MVP implementation tasks

Backend API and owner provisioning CLI are the first delivery. UI is deferred
to explicit follow-up tickets. This plan does not implement matching; KAN-18
remains the matching design task. A company may match several strategies while
retaining one conceptual Match per user/company. Recording per-strategy
contributions is a matching implementation decision, not a single-strategy
restriction.

Epic: [KAN-70](https://kawashreh.atlassian.net/browse/KAN-70).

| Ticket | Work | Prerequisites |
| --- | --- | --- |
| [KAN-49](https://kawashreh.atlassian.net/browse/KAN-49) | Planned migration tooling, deferred | Not a prerequisite for this MVP |
| [KAN-71](https://kawashreh.atlassian.net/browse/KAN-71) | Management API foundation and operational bootstrap schema | None in this workstream |
| [KAN-72](https://kawashreh.atlassian.net/browse/KAN-72) | Atomic provisioning and owner account CLI | KAN-71 |
| [KAN-73](https://kawashreh.atlassian.net/browse/KAN-73) | Authentication, sessions and ownership enforcement | KAN-72 |
| [KAN-74](https://kawashreh.atlassian.net/browse/KAN-74) | User and ProfessionalProfile management API | KAN-73 |
| [KAN-75](https://kawashreh.atlassian.net/browse/KAN-75) | ServiceOffering CRUD | KAN-73 |
| [KAN-76](https://kawashreh.atlassian.net/browse/KAN-76) | ICP CRUD with multi-value targeting | KAN-73 |
| [KAN-77](https://kawashreh.atlassian.net/browse/KAN-77) | Multiple active discovery strategies | KAN-75, KAN-76 |
| [KAN-78](https://kawashreh.atlassian.net/browse/KAN-78) | End-to-end verification, runbook and pre-MR review | KAN-74, KAN-77 |
| [KAN-79](https://kawashreh.atlassian.net/browse/KAN-79) | Follow-up UI: login, account settings and professional onboarding | KAN-78 |
| [KAN-80](https://kawashreh.atlassian.net/browse/KAN-80) | Follow-up UI: offerings, ICPs and strategies | KAN-78 |

KAN-74, KAN-75 and KAN-76 can proceed in parallel after the shared foundation.
BuyerPersona and EngagementPreferences remain planned separate domain
entities; their detailed workflows are deferred from this backend slice.

Implementation defaults in the tickets are proposals to make the work
actionable, not additional user-approved product requirements. KAN-71 must
document the selected framework, authentication contract and validation
schemas before downstream implementation. Defaults include opaque revocable
sessions, case-insensitive username uniqueness, inactive strategies on
creation, and conflict responses when deleting referenced offerings or ICPs.
ICP item shapes and empty-list semantics must be recorded explicitly.

Experience may capture optional dates/duration for relevance. The proposed
month-precision representation and current-work flag remain implementation
details to finalize with the collection schemas. Professional collections
stay in validated PostgreSQL JSONB on one profile row for this delivery.

Migration tooling remains planned under KAN-49, but is deferred from this
delivery and does not block KAN-71. Current development data is disposable;
update bootstrap SQL and explicitly recreate a development database as
needed. Existing-data migration and legacy-user backfill are not required
for this slice. Preserve schema referential integrity on fresh bootstrap.
Use a separate management development database so rebuilds do not interrupt
concurrent ELT work. Application startup must not automatically reset data.

Acceptance includes live Postgres bootstrap/ownership tests, full Python
3.14 compile and pytest/Ruff checks, independent review, and the repository's
pre-MR workflow. These tasks create no authorization to push or open an MR.
