# 0019: Business-owned recommendations with immutable assessments and offer history

Status: Accepted
Date: 2026-11-14
Deciders: Khaled Awashreh

## Context and Problem Statement

Creation-only Matches and immutable ranked recommendation batches describe
discovery differently. A batch item cannot by itself identify an unresolved
opportunity across reassessment, app presentation and weekly email. Treating
each batch as a new opportunity loses the connection between the explanation
shown and a later decision to pursue the company. Treating a company as
permanently delivered prevents legitimate repeat offers after cooldown.

Configuration previously belonged directly to User. The approved business
workflow distinguishes the authenticated Account, the person represented by
User, the owning Business and the shared Gold Company being considered as a
prospect. This extends ADR-0012's separation between shared company facts and
owner-specific assessment state.

The approved change defines the behavior contract. Its implementation and
deployment are tracked separately in the change checklist.

## Decision Drivers

1. Preserve the exact assessment and evidence behind feedback, email content
   and a user's explicit Save decision after company or configuration changes.
2. Apply company suppression consistently across strategies and delivery
   channels while keeping generation distinct from confirmed presentation.
3. Preserve personal information and configuration identities when introducing
   Business ownership, without inventing Business profile values.
4. Make concurrent and retried commands atomic in the existing PostgreSQL
   database with explicit repository and transaction boundaries.
5. Retain source/company identities and operational lineage during the
   replacement of disposable derived workflow data.

## Considered Options

1. A shared Business-owned recommendation collection, immutable assessment
   revisions, separate offer cycles and explicit prospects. (chosen)
2. Continue separate creation-only Matches and independent recommendation
   batches for discovery and email.
3. Use one mutable recommendation record for assessment, delivery and pursuit.

## Decision Outcome

Chosen option: 1. Stable discovery identity and immutable assessment history
preserve attribution while separate offer and pursuit records express changes
without rewriting their source explanation.

### Ownership and configuration

1. Account holds authentication. User represents the person. Each User has one
   Business, and each Business has one owning User. Business is distinct from
   the shared Gold Company pool.
2. Business stores its name, tagline, website, location, description and
   capabilities directly. Personal/contact fields and professional-profile
   collections retain their existing User ownership and values.
3. Offerings, ICPs, strategies, recommendations, suppression and prospects
   belong to Business. User actions retain separate acting-User attribution.
4. New User and sole Business creation is atomic. Credential-only Accounts do
   not require fabricated Users. Explicit, repeatable ownership setup attaches
   existing configuration without changing its IDs, values or associations.
   New Business profile fields remain unset until supplied.
5. Services and ICP editing use Profile/Settings. Strategies remain manual
   active/inactive offering-to-ICP bindings outside primary navigation and
   Profile. Automatic pairing and a new scoring algorithm are outside this
   change.

### Discovery, assessment and pursuit

1. Recommendation has a stable identity, with at most one open occurrence per
   Business/Company. Resolved history does not impose lifetime uniqueness on
   that pair. Save converts discovery to a prospect; Not relevant resolves it
   as rejected. Later pauses an open occurrence, and no action leaves it open.
2. Eligible reassessment appends an immutable revision to the same open
   occurrence. Each revision preserves its strategy/offering/ICP and personal
   profile context, policy versions, assessment components and evidence
   observation identities. A revision can retain several strategy assessments.
3. Frozen delivery references, quality feedback and prospect origins identify
   the exact revision shown. Current company eligibility and relationship state
   are presented separately from assessment-time facts.
4. Prospect is unique by Business/Company. Save atomically creates or reuses it,
   links the shown revision, resolves open discovery and records one logical
   action. Saving another historical origin preserves an existing prospect's
   stage and history.
5. Pursuit uses versioned current state plus append-only activity. Adjacent
   stage changes, backward reasons, closure and reopening follow the approved
   transition table. Occurrence and recording times remain separate;
   corrections append history. Feedback reports do not execute pursuit
   commands, change ranking policy or send outreach.

### Suppression and publication

1. Cooldown, pause, rejection, relationship and uncertain-delivery protection
   are independent Business/Company blocks. Clearing one does not clear the
   others. Closed and won relationships remain outside new-prospect discovery.
2. The configurable repeat interval defaults to 30 days. First confirmed app
   presentation or successful SMTP handoff starts cooldown. Generation,
   reassessment, ordinary reads and reopening do not start or restart it.
3. Recommendation runs skip reassessment and renewed offering during cooldown.
   The next eligible run after expiry can reconsider current evidence. Expiry
   does not execute a separate company scheduler or guarantee selection.
4. A renewed offer selects a revision in a new offer cycle while retaining the
   original first-presentation time. Weekly email projects the shared
   collection, includes each Company at most once, and respects the same
   cooldown even for a still-open recommendation.
5. App and email acquire a shared Business/Company offer claim without claiming
   exposure. Preparing has a bounded lease and owner token. Sending and Unknown
   do not expire into automatic resend. Settlement and explicit recovery retain
   the distinction between actual presentation and later recording time.
6. The final serialized email authorization validates consent, recipient,
   membership and company blocks before transport. Decisions committed before
   authorization prevent sending. Authorization is followed by bounded SMTP
   outside the database transaction; later decisions do not guarantee recall.

### Evidence, transactions and release

1. Collection materializes shared source data before explicit source-currentness
   reconciliation makes changed observations usable through guarded evidence.
   Recommendation reads and commands do not collect or reconcile source data.
2. Services consume repository Protocols and existing transaction boundaries.
   Models and pure policies remain independent of database/network clients and
   presentation. Concrete SQL and composition remain in their owning layers.
3. Workflow writes serialize by Business/Company and retain database uniqueness
   and membership constraints. Request keys and canonical payload fingerprints
   distinguish retries from changed intent. Retries retain the committed
   outcome; optimistic versions protect newer pursuit edits.
4. Cutover replaces the creation-only writer and explicitly scopes obsolete
   workflow cleanup. It does not convert old Matches into saved prospects or
   reset Bronze, Silver, Gold, account/configuration or operational lineage.
   Target inspection determines whether cleanup is needed; empty targets are a
   no-op. Deployment ordering and rollback preserve new history and suppression.

### Consequences

1. Good: one explanation can be followed from discovery through presentation,
   explicit pursuit and later activity without overwriting its history.
2. Good: a new strategy or channel cannot bypass a Business's company blocks,
   while eligible repeat offers remain possible after cooldown.
3. Good: Business ownership can evolve independently from personal identity
   and the shared source/company corpus.
4. Bad: revisions, cycles, receipts and activity require more relational
   constraints and transaction checks than an immutable batch alone.
5. Bad: uncertain transport requires explicit recovery; elapsed time cannot
   safely prove that an email was not accepted.

## Pros and Cons of the Options

### Shared collection with revisions, cycles and prospects

1. Good: separates stable identity, immutable explanation, actual offering and
   manual pursuit while preserving their references.
2. Bad: requires coordinated cutover, explicit ownership setup and concurrency
   verification across all writers.

### Independent Matches and recommendation batches

1. Good: retains the existing writer and batch storage shapes.
2. Bad: competing qualification and delivery histories cannot provide one
   coherent discovery-to-pursuit identity or shared repeat protection.

### One mutable recommendation record

1. Good: minimizes the initial number of records and ordinary reads.
2. Bad: reassessment and current pursuit edits can rewrite the explanation
   actually shown, while one delivery timestamp cannot represent renewed offers
   and uncertain transport.

## Related

1. [Approved change design](../openspec/changes/recommendation-prospect-workflow/design.md)
   and its behavior specification and implementation checklist.
2. [ADR-0012](0012-icp-verdict-not-on-company-dimension.md), shared company facts
   and owner-specific verdicts.
3. [Architecture sections 4 and 9](../docs/architecture.md), pipeline and
   operational boundaries.
4. [Management runtime](0015-management-fastapi-runtime.md) and
   [browser foundation](0016-browser-foundation-and-session-bootstrap.md).
