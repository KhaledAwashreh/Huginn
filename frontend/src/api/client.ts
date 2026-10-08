import { normalizeApiError } from './normalizeApiError';

interface ApiClientConfiguration {
  getCsrfToken?: () => string | undefined;
  onUnauthorized?: () => void;
  getIdentityVersion?: () => number;
}
interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  anonymous?: boolean;
}
let configuration: ApiClientConfiguration = {};
export function configureApiClient(next: ApiClientConfiguration): void {
  configuration = next;
}

export async function apiRequest<T = void>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  if (!path.startsWith('/api/') || path.startsWith('//') || path.includes('\\'))
    throw new Error('Only local API paths are allowed.');
  const method = options.method ?? 'GET';
  const requestConfiguration = configuration;
  const identityVersion = requestConfiguration.getIdentityVersion?.();
  const headers = new Headers({ Accept: 'application/json' });
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');
  if (method !== 'GET' && !options.anonymous) {
    const proof = configuration.getCsrfToken?.();
    if (!proof) throw new Error('Reload the page before trying again.');
    headers.set('X-CSRF-Token', proof);
  }
  const init: RequestInit = { method, headers, credentials: 'same-origin', redirect: 'error' };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  if (options.signal) init.signal = options.signal;
  const response = await fetch(path, init);
  if (identityVersion !== requestConfiguration.getIdentityVersion?.()) {
    throw new Error('The session changed. Reload before trying again.');
  }
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (
      response.status === 401 &&
      identityVersion === requestConfiguration.getIdentityVersion?.()
    ) {
      requestConfiguration.onUnauthorized?.();
    }
    throw normalizeApiError(response.status, body);
  }
  if (response.status === 204) return undefined as T;
  const body = (await response.json()) as T;
  if (identityVersion !== requestConfiguration.getIdentityVersion?.()) {
    throw new Error('The session changed. Reload before trying again.');
  }
  return body;
}
