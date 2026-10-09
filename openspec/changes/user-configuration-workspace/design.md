## Context

See [proposal.md](proposal.md). The inspected layered implementation at `.worktrees/simple-matchmaking` `ca2ddd9` already implements all requested configuration CRUD; this change is primarily frontend. Read `docs/entities.md`, `docs/management-foundation.md`, API routers/requests/responses, and `application/services/{user_profile,service_offerings,ideal_client_profiles,discovery_strategies}.py`. No separate CRUD server should be introduced.

WIP entities do not equate to implemented capabilities. BuyerPersona and EngagementPreferences are mentioned as separate concepts but have no current routes; Match workflows, scoring/feedback/activity, evidence, contributions, occurrences, digest, and resurfacing remain outside this phase.

## Goals / Non-Goals

**Goals:** Accurate editors against implemented schemas, clear references and save behavior, ownership-safe server queries.

**Non-Goals:** New targeting taxonomy, matching-rule changes, standalone company directory, CRM, optimistic concurrency/version schema, autosave, or new business entities. A narrow read-only collected-company search supplies exclusion labels. Region targeting remains stored but current matcher skips it according to its existing rules; do not solve that behavior in the editor.

## Decisions

### 1. Entity editors stay separate

| Frontend placement | Page and server contract |
| --- | --- |
| `features/configuration/account/` | `/account`: GET/PATCH `/api/v1/me`, PATCH `/api/v1/me/password` |
| `features/configuration/professional-profile/` | `/professional-profile`: GET/PATCH `/api/v1/me/professional-profile` |
| `features/configuration/offerings/` | `/offerings`: CRUD `/api/v1/offerings[/{id}]` |
| `features/configuration/ideal-client-profiles/` | `/icps`: CRUD `/api/v1/ideal-client-profiles[/{id}]` |
| `features/configuration/discovery-strategies/` | `/strategies`: CRUD `/api/v1/discovery-strategies[/{id}]`, existing `active` list filter |

Each feature owns its typed queries, mutation adapters, draft form, list/editor pages, and tests. Common field feedback/headers/status UI come from foundation. Do not create an umbrella models file or a dynamic form schema to render unrelated entities. The UI name Service offerings preserves domain meaning while exact API path remains `/offerings`.

### 2. Preserve exact field shapes

Personal fields use existing Email/E164Phone/IANA validation; optional timezone clears with null. Profile optional text clears with null, while arrays clear with `[]`. Map empty nullable text to explicit null only when user actually clears it; never send null for required values. Experiences preserve dates' YYYY-MM representation and array order; name-only skills do not gain levels/proficiency. Keep API response IDs and timestamps out of mutation bodies. Use typed diff against original fetched values and omit unchanged fields; an empty PATCH is not submitted.

Offerings use name/description. ICP arrays preserve the existing object shapes: industries `{name}`, sizes `{band}`, geographies `{kind:"country"|"region",value}`, exclusions `{kind:"company",company_id}`, `{kind:"industry",name}`, or `{kind:"geography",geography:{kind,value}}`. No free-form JSON editor is required; use repeated grouped fields and explicit Add/remove controls. Size bands are four multiple toggles; industries and countries use searchable multi-selects from live collected Gold values. Company exclusions select collected company labels with bounded name/domain search and selected-ID lookup. No new region entry is offered. Existing region and absent catalogue values remain unchanged until explicitly removed, with an unsupported-by-current-matcher warning. Do not promise which company will match or change exclusion scope/precedence.

Strategy form selects one offering and one ICP and sets is_active; default inactive. Paginated reference selectors request max 100 rows with Load more/search over loaded values and continued paginated retrieval, never assume page1 complete. Preserve selected references that are not on the current loaded page via owner-scoped item GET; a 404 reports removed/unavailable rather than substituting another choice. Creating a missing offering/ICP is a local navigation action with dirty-draft protection, not embedded backend provisioning.

### 3. Draft and feedback contract

Use PrimeVue form controls and shared field feedback. Fetched data initializes a local typed draft once; background refresh does not mutate it. Save serializes exact changed fields, disables duplicate submissions, and on success replaces baseline with server response then invalidates affected queries. Cancel restores baseline. Dirty-route transitions have explicit leave/stay confirmation, with browser unload warning only while dirty. No autosave.

Native 422 loc paths map to nested row/field feedback; domain 422 may be generic, so show safe form-level guidance rather than inventing field blame. 403 is permission/CSRF with reload guidance; 401 is foundation session-expiry flow. 409 for referenced offering/ICP deletion directs the user to strategies, does not delete locally, and does not expose other owners' references. Network loss keeps draft and offers Refresh saved data before a deliberate retry; mutations have automatic retry disabled. Existing concurrent last-writer behavior remains; no invented row versions.

### 4. Account and lifecycle integration

Account page separates personal details and password security. Foundation supplies logout. Password change submits current/new only, never cached; success clears sessions/private cache and returns to login. When lifecycle module is installed, read `/api/v1/me/account-security` for read-only username, verification and recovery email, explain contact/recovery distinction, and use its initial enrollment action for trusted owners without a verified address. This optional section is owned by lifecycle integration, not a duplicate security endpoint here. Existing accounts can use workspace before lifecycle ships.

### 5. Layout and tests

Forms use grouped sections, modest widths, explicit Save changes/Cancel, and arrays with clear row labels. Lists use name, short description/criteria summary, status where meaningful, and actions; long text wraps or opens detail, not clipped tooltips only. Narrow layouts stack forms and provide horizontal scrolling or detail views for tables. Test changes against real request shapes, nested validation, delete 409, pagination beyond 100, explicit clears, session expiry and uncertain save. Browser verification covers keyboard/wide/narrow layouts and representative sparse/long data; mock data are clearly fixtures, not claims of live integration.

## Risks / Trade-offs

- [WIP entity scope creep] → Only implemented definitions receive editors; module inventory names deferred concepts explicitly.
- [Profile email mistaken as recovery identity] → Distinct labels/explanation and lifecycle-owned read-only recovery data.
- [Large reference lists] → Bounded server paging plus load-more access, owner GET for selected IDs.
- [PATCH semantic loss] → Typed diff, explicit clear controls, realistic contract tests.

## Migration Plan

No schema migration or server CRUD changes. Narrow authenticated read-only collected-options endpoints support the revised selectors. Deploy foundation first, then editor routes. Build against actual layered-management OpenAPI types and run frontend/backend regression checks. Disable routes on rollback; user data remain unchanged. Test with dedicated disposable PostgreSQL 16 data and never reset shared operational or Gold tables.

## Shared standards dependency

The authoritative [foundation implementation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) govern this change: exact Node/npm/dependency locks, strict TypeScript, naming, offline schema drift, lint/format/test/CI/hook gates, WCAG 2.2 AA target, and Python layer placement. Consume shared components and transport; do not introduce divergent tooling or duplicate session/database ports. The inventories below define the new production files/types for this feature. Package `__init__.py` markers are empty, not public re-export umbrellas. Test files mirror these use cases and add the behavior scenarios already specified in this design.

## Exact configuration inventory

Relative to `frontend/src/features/configuration/`. Existing backend CRUD/request/response/validation files are consumed unchanged. Each API function has its own module; entity draft files are local form types, not umbrella copies of transport schemas. Forms reuse foundation `useDirtyDraft` and shared feedback.

| Exact path | Named types / exports |
| --- | --- |
| `account/pages/AccountPage.vue` | AccountPage |
| `account/components/AccountForm.vue` | AccountForm |
| `account/forms/accountDraft.ts` | AccountDraft |
| `account/forms/serializeAccountPatch.ts` | serializeAccountPatch |
| `account/composables/useAccount.ts` | useAccount |
| `account/api/getAccount.ts` | getAccount; generated request/response contracts |
| `account/api/updateAccount.ts` | updateAccount; generated request/response contracts |
| `account/api/changePassword.ts` | changePassword; generated request/response contracts |
| `professional-profile/pages/ProfessionalProfilePage.vue` | ProfessionalProfilePage |
| `professional-profile/components/ProfessionalProfileForm.vue` | ProfessionalProfileForm |
| `professional-profile/forms/professionalProfileDraft.ts` | ProfessionalProfileDraft |
| `professional-profile/forms/serializeProfessionalProfilePatch.ts` | serializeProfessionalProfilePatch |
| `professional-profile/composables/useProfessionalProfile.ts` | useProfessionalProfile |
| `professional-profile/api/getProfessionalProfile.ts` | getProfessionalProfile; generated request/response contracts |
| `professional-profile/api/updateProfessionalProfile.ts` | updateProfessionalProfile; generated request/response contracts |
| `offerings/pages/ServiceOfferingListPage.vue` | ServiceOfferingListPage |
| `offerings/pages/ServiceOfferingEditorPage.vue` | ServiceOfferingEditorPage |
| `offerings/components/ServiceOfferingForm.vue` | ServiceOfferingForm |
| `offerings/forms/serviceOfferingDraft.ts` | ServiceOfferingDraft |
| `offerings/forms/serializeServiceOfferingPatch.ts` | serializeServiceOfferingPatch |
| `offerings/composables/useServiceOffering.ts` | useServiceOffering |
| `offerings/api/listServiceOfferings.ts` | listServiceOfferings; generated request/response contracts |
| `offerings/api/getServiceOffering.ts` | getServiceOffering; generated request/response contracts |
| `offerings/api/createServiceOffering.ts` | createServiceOffering; generated request/response contracts |
| `offerings/api/updateServiceOffering.ts` | updateServiceOffering; generated request/response contracts |
| `offerings/api/deleteServiceOffering.ts` | deleteServiceOffering; generated request/response contracts |
| `ideal-client-profiles/pages/IdealClientProfileListPage.vue` | IdealClientProfileListPage |
| `ideal-client-profiles/pages/IdealClientProfileEditorPage.vue` | IdealClientProfileEditorPage |
| `ideal-client-profiles/components/IdealClientProfileForm.vue` | IdealClientProfileForm |
| `ideal-client-profiles/forms/idealClientProfileDraft.ts` | IdealClientProfileDraft |
| `ideal-client-profiles/forms/serializeIdealClientProfilePatch.ts` | serializeIdealClientProfilePatch |
| `ideal-client-profiles/composables/useIdealClientProfile.ts` | useIdealClientProfile |
| `ideal-client-profiles/api/listIdealClientProfiles.ts` | listIdealClientProfiles; generated request/response contracts |
| `ideal-client-profiles/api/getIdealClientProfile.ts` | getIdealClientProfile; generated request/response contracts |
| `ideal-client-profiles/api/createIdealClientProfile.ts` | createIdealClientProfile; generated request/response contracts |
| `ideal-client-profiles/api/updateIdealClientProfile.ts` | updateIdealClientProfile; generated request/response contracts |
| `ideal-client-profiles/api/deleteIdealClientProfile.ts` | deleteIdealClientProfile; generated request/response contracts |
| `discovery-strategies/pages/DiscoveryStrategyListPage.vue` | DiscoveryStrategyListPage |
| `discovery-strategies/pages/DiscoveryStrategyEditorPage.vue` | DiscoveryStrategyEditorPage |
| `discovery-strategies/components/DiscoveryStrategyForm.vue` | DiscoveryStrategyForm |
| `discovery-strategies/forms/discoveryStrategyDraft.ts` | DiscoveryStrategyDraft |
| `discovery-strategies/forms/serializeDiscoveryStrategyPatch.ts` | serializeDiscoveryStrategyPatch |
| `discovery-strategies/composables/useDiscoveryStrategy.ts` | useDiscoveryStrategy |
| `discovery-strategies/api/listDiscoveryStrategies.ts` | listDiscoveryStrategies; generated request/response contracts |
| `discovery-strategies/api/getDiscoveryStrategy.ts` | getDiscoveryStrategy; generated request/response contracts |
| `discovery-strategies/api/createDiscoveryStrategy.ts` | createDiscoveryStrategy; generated request/response contracts |
| `discovery-strategies/api/updateDiscoveryStrategy.ts` | updateDiscoveryStrategy; generated request/response contracts |
| `discovery-strategies/api/deleteDiscoveryStrategy.ts` | deleteDiscoveryStrategy; generated request/response contracts |
| `account/components/PasswordSecurityForm.vue` | PasswordSecurityForm |
| `account/forms/passwordChangeDraft.ts` | PasswordChangeDraft; secret local only |
| `professional-profile/components/ExperienceRows.vue` | ExperienceRows |
| `professional-profile/components/SkillRows.vue` | SkillRows |
| `professional-profile/components/PreviousProjectRows.vue` | PreviousProjectRows |
| `ideal-client-profiles/components/IndustryRows.vue` | IndustryRows |
| `ideal-client-profiles/components/CompanySizeRows.vue` | CompanySizeRows |
| `ideal-client-profiles/components/GeographyRows.vue` | GeographyRows |
| `ideal-client-profiles/components/ExclusionRows.vue` | ExclusionRows |
| `discovery-strategies/components/OfferingReferenceSelect.vue` | OfferingReferenceSelect |
| `discovery-strategies/components/IcpReferenceSelect.vue` | IcpReferenceSelect |
| `discovery-strategies/composables/useStrategyReferences.ts` | useStrategyReferences; bounded paging/selected owner GET |
| `routes.ts` | configurationRoutes |

## Revised selector contract (explicit user follow-up)

The follow-up supersedes the original free-text ICP controls. Live Gold industry/country values are presented exactly as collected, excluding null/blank industry/country values and the `Unspecified` industry sentinel. Values such as `USA` and `United States` remain distinct; no ISO mapping or hidden normalization is performed. Counts mean collected company coverage for each value, not predicted combined matches.

Industry and country controls use searchable PrimeVue MultiSelect with chips and no default/select-all targeting. The four size bands use multiple SelectButton toggles. Within a criterion category matching uses OR, across industry/size/country it uses AND; empty categories can be saved but clearly show incomplete matching criteria. Existing matcher behavior and offering/strategy references remain unchanged. Regions currently make strategies unsupported/skipped and cannot be newly added.

Existing absent/legacy values, array order and duplicates survive background options fetches and unrelated edits. Explicit deselection removes that value's rows; selecting new values appends their existing structured request shapes. Exclusions follow the same rule by category, preserving untouched kinds and original order. Company exclusions use name/domain labels from a bounded searchable page; a selected UUID outside current pages is resolved by item GET. Missing companies stay visibly unavailable until explicitly removed, while transport/auth errors remain loading failures.

GET `/api/v1/configuration-options` returns industry/country/size value+company_count arrays. GET `/api/v1/configuration-options/companies` accepts bounded search/offset/limit, and GET `/api/v1/configuration-options/companies/{company_id}` resolves selected labels. All three require the existing authenticated session, read only collected Gold fields and do not expose operational owners/accounts. Existing unit-of-work/database/session boundaries are reused; no driver import outside the existing client.

Experience supports one newly selected current role at a time. Selecting Current role explicitly clears end_month, displays Present in a disabled end-month control, and disables current selection on the other rows until unchecked. Existing saved flags are preserved on initialization. No backend professional-profile invariant or matcher rule is changed by this UI refinement.

### Additional support inventory

Backend paths below are relative to `src/huginn/management/`:

| Exact path | Named type/export |
| --- | --- |
| `application/read_models/configuration_options.py` | ConfigurationOptions |
| `application/read_models/configuration_option.py` | ConfigurationOption |
| `application/read_models/company_option.py` | CompanyOption |
| `application/requests/get_configuration_options_request.py` | GetConfigurationOptionsRequest |
| `application/requests/list_company_options_request.py` | ListCompanyOptionsRequest |
| `application/requests/get_company_option_request.py` | GetCompanyOptionRequest |
| `application/responses/get_configuration_options_response.py` | GetConfigurationOptionsResponse |
| `application/responses/list_company_options_response.py` | ListCompanyOptionsResponse |
| `application/responses/get_company_option_response.py` | GetCompanyOptionResponse |
| `application/protocols/configuration_options_query.py` | ConfigurationOptionsQuery |
| `application/services/get_configuration_options_service.py` | GetConfigurationOptionsService |
| `application/services/list_company_options_service.py` | ListCompanyOptionsService |
| `application/services/get_company_option_service.py` | GetCompanyOptionService |
| `persistence/row_models/configuration_option.py` | ConfigurationOptionRow |
| `persistence/row_models/company_option.py` | CompanyOptionRow |
| `persistence/repositories/configuration_options_query.py` | PostgresConfigurationOptionsQuery |
| `presentation/api/responses/configuration_option.py` | ConfigurationOptionResponse |
| `presentation/api/responses/configuration_options.py` | ConfigurationOptionsResponse |
| `presentation/api/responses/company_option.py` | CompanyOptionResponse |
| `presentation/api/routers/configuration_options.py` | router |

Existing app.py is narrowly extended for composition; generated schema/types are regenerated together. Browser fixture/config origin ports become configurable so disposable fixtures run separately from the active real-data workspace.

Frontend follow-up paths below are relative to `frontend/src/features/configuration/ideal-client-profiles/`:

| Exact path | Named type/export |
| --- | --- |
| `api/getConfigurationOptions.ts` | getConfigurationOptions; ConfigurationOption; ConfigurationOptions |
| `api/listCompanyOptions.ts` | listCompanyOptions; CompanyOption; CompanyOptionPage |
| `api/getCompanyOption.ts` | getCompanyOption |
| `composables/useConfigurationOptions.ts` | useConfigurationOptions |
| `forms/collectedOptionSelection.ts` | mergeCollectedValues |
| `components/CompanyExclusionSelect.vue` | CompanyExclusionSelect |

Existing row controls, IdealClientProfileForm and ExperienceRows are refined in place. Counts remain in option menus while selected chips and size toggles use compact values. Playwright can reuse an installed browser via optional `HUGINN_BROWSER_EXECUTABLE` without downloads.
