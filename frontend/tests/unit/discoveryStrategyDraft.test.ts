import { describe, expect, it } from 'vitest';
import { serializeDiscoveryStrategyPatch } from '@/features/configuration/discovery-strategies/forms/serializeDiscoveryStrategyPatch';
const baseline = {
  name: 'Founders',
  service_offering_id: 'offering-1',
  ideal_client_profile_id: 'icp-1',
  is_active: false,
};
describe('strategy changed-field serialization', () => {
  it('omits unchanged fields and includes an explicit false active clear', () => {
    expect(serializeDiscoveryStrategyPatch(baseline, baseline)).toEqual({});
    expect(serializeDiscoveryStrategyPatch({ ...baseline, is_active: true }, baseline)).toEqual({
      is_active: false,
    });
  });
  it('does not include response ownership or identity fields', () => {
    expect(
      serializeDiscoveryStrategyPatch(baseline, { ...baseline, name: 'New strategy' }),
    ).toEqual({ name: 'New strategy' });
  });
});
