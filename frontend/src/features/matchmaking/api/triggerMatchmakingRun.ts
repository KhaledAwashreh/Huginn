import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type TriggerMatchmakingBody = components['schemas']['TriggerRunBody'];
export type MatchmakingRunReceipt = components['schemas']['RunReceiptResponse'];

export const triggerMatchmakingRun = (body: TriggerMatchmakingBody) =>
  apiRequest<MatchmakingRunReceipt>('/api/v1/admin/matchmaking/runs', {
    method: 'POST',
    body,
  });
