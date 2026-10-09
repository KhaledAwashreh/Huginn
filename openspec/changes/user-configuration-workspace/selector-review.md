# Collected selector follow-up review

Final verdict: no remaining actionable findings in the collected ICP selectors, their read-only backend, or the current Experience refinement. Reviewed the completed snapshot on 2026-10-09 against `design.md` section "Revised selector contract" and the amended specification.

Scope: collected industry/country/size options, grouped exclusions, company paging and selected-ID lookup, option-loading draft preservation, authenticated Gold reads, generated API shapes, and current-role controls. The previously reviewed workspace implementation was outside this follow-up.

## Findings and resolutions

| Finding | Resolution verified in final source |
| --- | --- |
| Geography controls allowed new regions and editing saved regions. | `GeographyRows.vue` has only read-only saved region labels and explicit removal. |
| Saved region exclusions were retained without a removal control. | `ExclusionRows.vue` visibly renders saved regions with removal controls, preserving other rows and their order. |
| MultiSelect inherited select-all targeting. | All four industry/country MultiSelect controls set `show-toggle-all` to false. |
| Country controls filtered the industry-only `Unspecified` sentinel. | Country selectors retain nonblank exact collected country values; sentinel filtering is industry-only. |
| Exclusion guidance claimed AND across exclusion categories and understated region behavior. | Guidance states that any matching exclusion rejects a company and any region entry skips the whole strategy as unsupported, matching the unchanged evaluator and candidate SQL. |
| A disabled selected-ID query could show an indefinite loading label despite a matching loaded company. | Loading uses `isFetching` and requires no resolved company. Loaded page data takes precedence over selected-ID errors. |
| Saved company selection disappeared when a search returned no hits. | The picker renders resolved selected companies or disabled saved-value fallbacks independently of search-result count. A 404 is distinguished from transport/authentication failure. |
| Failed metadata GETs lacked private cache headers. | Existing exception handlers apply `no-store` and `Vary: Cookie` to the configuration-options paths, including authentication, not-found, validation, and unexpected errors. Successful routes also set the headers. |
| PrimeVue's default chip removal could remain active while saving. | All four MultiSelect controls use custom Chip slots with `removable` false when disabled. |

## Verification

1. Independently ran `rtk npm run test:unit -- tests/components/configuration/BusinessDefinitionForms.test.ts tests/components/configuration/ExperienceRows.test.ts tests/unit/configuration/collectedOptionSelection.test.ts`: 3 files and 6 tests passed.
2. Read the metadata integration test and final router, services, Protocol, read models, strict row models, adapter, app wiring, and generated route/type entries. Queries read Gold only, use the existing database session and unit of work, count distinct companies for industry coverage, preserve raw country values, and bind bounded company-search parameters with literal substring matching. No operational owner/account fields are exposed.
3. Checked selector merge functions and form initialization. Options fetches and failures change available labels and loading state without resetting the draft. Untouched duplicate/legacy rows retain their order; explicit value deselection removes that value's rows; new values append structured rows.
4. Checked Experience initialization and controls. Saved current flags remain unchanged on load. Explicit current selection clears the actual end month, displays disabled Present, and disables other non-current toggles until unchecked.
5. Parent reported full frontend 118-test and backend 1,419-test gates passing. Those broader runs were not independently rerun by this reviewer.

Browser verification remains owned by the parent run on disposable alternate ports. This review did not access or modify the active user runtime, download dependencies, change source, or commit.

## Contrast follow-up

Reviewed the later `CompanySizeRows.vue` rule `.rows :deep(.p-togglebutton:not(:disabled)) { color: var(--color-text); }`. It is confined to enabled size-band buttons in this component and uses the existing `#172b22` text token. The installed Aura light-theme buttons use light surface backgrounds in normal, hover, and selected states; dark mode is disabled by the app. Disabled colors, selected-state backgrounds, focus styles, and selection behavior remain intact. No actionable finding from this CSS change. The parent browser run owns measured contrast validation; this reviewer checked the source and installed theme definitions without repeating browser or semantic tests for this color-only edit.
