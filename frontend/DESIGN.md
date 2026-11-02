# Huginn workspace design

## Foundation

Use the MIT PrimeVue 4 Aura preset with a dark green primary action. The application
tokens in `src/shared/theme/tokens.css` define system sans typography, 16px body,
14px helper/status text, 24px page titles, 1.5 line height, a 4px spacing rhythm,
8px radii and a 1120px main column. The sign-in card is at most 400px wide.
Surfaces are white with restrained borders. Status always includes text.

## Shell

1. The top navigation holds the brand, Matches, Profile and the user menu. Matches is
   home. Pages that the navigation already names keep their h1 for screen readers only.
2. The top bar shows the current page's title and breadcrumbs from route metadata.
   `PageHeader` publishes the title through the key in `src/shared/navigation/pageTitle.ts`.
3. Settings is a modal, not a page. The user menu or a page opens it at a section (Account,
   ICP definition, Security and, for administrators, Admin) through `openSettingsKey`. Its
   body scrolls inside the modal, and it asks before discarding unsaved changes. Admin
   tools are full pages that open behind it.

## Matches

1. Matches are a grid of tiles; the whole tile opens the match detail page.
2. Search filters the current page only, and its empty message says so. Pagination sits
   outside the grid and empty states, so Next and Previous remain when a search finds
   nothing on this page.

## Profile

1. Profile reads as a business page; items are edited in dialogs, not inline.
2. About, Services, Skills and the ICP tile are backed by the API. The ICP tile and its
   add action open the settings modal.
3. A section whose load fails shows ErrorState with a retry, never its empty placeholder.
4. A service change that ends in a 5xx or network error has an uncertain outcome, so the
   dialog asks for a refresh before any retry.

## Disabled until backend

UI without a backend stays visible but disabled rather than pretending to work.

1. Controls are native disabled buttons with `title="Coming soon"`, gated on the single
   constant in `src/shared/availability/awaitingBackend.ts`.
2. This covers match thumbs up and down, and on Profile the business card, Leadership,
   Clients and Links, including their add and row actions.
3. Copy with no data states what is true ("Client list is coming soon."), not a promise
   the user can act on. ICP annotations are hidden while empty.
4. These features hold in-memory state only. Nothing about them is written to
   `localStorage` or any other store, and file upload is not offered.

## Accessibility and states

Every page has one h1. Navigation changes focus to that heading; the shell's
skip link reaches main content. Visible focus rings, visible form labels,
username/current-password autocomplete, native paste and keyboard controls
support authentication. Pending buttons prevent duplicate submission. Errors
use alert feedback. Sign-in failure preserves the username and clears the password.

Use PageHeader, FieldFeedback, LoadingState, EmptyState, ErrorState and StatusLabel
for shared states. `useDirtyDraft` keeps background refresh separate from edits,
asks before discarding changes, and warns on browser departure only while dirty.
Query data is cleared when identity or session proof changes. A 403 retains
identity and drafts and asks for reload; mutations are never automatically replayed.

The accessibility target is WCAG 2.2 AA. Playwright/axe covers representative
login, error and workspace states, 320px reflow, keyboard focus and reduced motion.
Automated scans supplement manual inspection; they do not establish conformance.
Recorded verification and screenshot inspection belong in the implementation log.
