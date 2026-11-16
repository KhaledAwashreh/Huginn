// Keep unsupported actions disabled until their owning backend contract exists.
export const AWAITING_BACKEND_SUPPORT = true;

export const awaitingBackendAttrs = AWAITING_BACKEND_SUPPORT ? { disabled: true } : {};
