export function prospectsEnabled(): boolean {
  return import.meta.env.VITE_HUGINN_PROSPECTS_ENABLED === 'true';
}
