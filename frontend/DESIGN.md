# Huginn workspace design

The foundation provides sign-in, sign-out and one workspace route. Later changes
add configuration and administrator routes through router metadata; the shell
does not advertise unfinished editors.

Use the MIT PrimeVue 4 Aura preset with a dark green primary action. The application
tokens in `src/shared/theme/tokens.css` define system sans typography, 16px body,
14px helper/status text, 24px page titles, 1.5 line height, a 4px spacing rhythm,
8px radii and a 1120px main column. The sign-in card is at most 400px wide.
Surfaces are white with restrained borders. Status always includes text.

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
