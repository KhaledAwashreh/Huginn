## 1. Typed feature integration

- [x] 1.1 Apply after foundation and existing layered CRUD, preserving actual API paths; verify generated schemas and route inventory match `/me`, `/me/professional-profile`, `/offerings`, `/ideal-client-profiles`, `/discovery-strategies`.
- [x] 1.2 Add separate feature query/mutation/draft modules and routable configuration tabs; verify ownership-scoped keys, local drafts and missing-resource 404 states.

## 2. Personal and professional editors

- [x] 2.1 Add personal-details editor with existing required fields and nullable timezone; verify changed-field PATCH, explicit null clear and safe validation without ownership/role/status mutation fields.
- [x] 2.2 Add password-change editor using current/new password only; verify success clears private session/cache and failure shows safe guidance without storing passwords.
- [x] 2.3 Add headline/summary and repeated skill/experience/project editors; verify exact object fields, order/duplicates, YYYY-MM validation, current-role/end-month conflict and null-versus-empty-array clear semantics.

## 3. Business definition editors

- [x] 3.1 Add offerings list/create/edit/delete with bounded pagination; verify required name/description, explicit confirmation, delete 409 preserves referenced offering and successful mutations update page state.
- [x] 3.2 Add ICP editor with all discriminated geography/exclusion types and exact size bands; verify structured request shape, region warning, collected company labels with retained saved UUID references, empty-array clears and referenced-delete 409.
- [x] 3.3 Add strategy editor and active filter/control with one offering/one ICP and inactive default; verify all reference options beyond 100 are reachable and unavailable selected references are not substituted.
- [x] 3.4 Add shared feature save/cancel/dirty-navigation handling and nested 422 feedback; verify background refetch, failure and uncertain response preserve draft and never auto-replay mutation or trigger matching/scraping.

## 4. Integration and visual validation

- [x] 4.1 Add optional lifecycle account-security section only when its API is installed; verify workspace remains usable by provisioned accounts independently of public signup and contact/recovery emails are distinctly labeled.
- [x] 4.2 Exercise ownership, editor clears, references, pagination and password session revocation against disposable PostgreSQL 16 API/browser fixtures; verify cross-user IDs return 404 and no shared data reset occurs.
- [x] 4.3 Inspect realistic long/sparse/list data, wide/narrow layouts and keyboard form/table flow; verify clipping/focus/error/action states and document rendered evidence in local implementation log.
- [x] 4.4 Run frontend type/lint/build/interaction tests, Python 3.14 compilation, Ruff check/format, full pytest with live PostgreSQL 16 regressions, strict OpenSpec validation and exact file/type inventory/dependency review against the chosen implementation base and fresh Sol high review; resolve findings before separately authorized commit/push.

## 5. Follow-up selector refinements

- [x] 5.1 Add authenticated read-only live Gold criterion options and bounded company search/selected lookup using existing management layers; verify exact values/counts, filtering and no operational owner exposure.
- [x] 5.2 Replace ICP free-text/repeated category controls with collected searchable multiselects, size toggles and structured company exclusions; preserve legacy/order/duplicates and exact PATCH shapes.
- [x] 5.3 Refine Experience Current role interaction to one selected current role, clear end month and display Present; verify disabled/re-enable behavior without silently rewriting loaded flags.
- [x] 5.4 Run focused meaningful regression checks and required frontend/backend/schema/OpenSpec/browser gates on disposable fixtures, scoped fresh Sol high review, and safely refresh only the owned live API.
