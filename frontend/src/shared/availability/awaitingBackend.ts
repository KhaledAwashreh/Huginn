// Product decision: UI without a backend stays visible but disabled rather than pretending to
// work. Covers match reactions and Profile's business details, leaders, clients and links.
// Lives in shared because both the matches and profile features gate on it.
export const AWAITING_BACKEND_SUPPORT = true;

// Bound onto native buttons, so they are truly disabled and explain why.
export const awaitingBackendAttrs = AWAITING_BACKEND_SUPPORT
  ? { disabled: true, title: 'Coming soon' }
  : {};
