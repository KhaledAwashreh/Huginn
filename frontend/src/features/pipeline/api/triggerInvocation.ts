import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type TriggerInvocationResponse = components['schemas']['InvocationReceiptResponse'];

export const triggerInvocation = (requestId: string): Promise<TriggerInvocationResponse> =>
  apiRequest('/api/v1/admin/pipeline/invocations', {
    method: 'POST',
    body: { request_id: requestId },
  });
