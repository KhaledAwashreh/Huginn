import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../src/api/apiError';
import ServiceOfferingForm from '../../../src/features/configuration/offerings/components/ServiceOfferingForm.vue';
import IdealClientProfileForm from '../../../src/features/configuration/ideal-client-profiles/components/IdealClientProfileForm.vue';
import type { components } from '../../../src/api/generated/schema';

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}));

afterEach(() => vi.clearAllMocks());
const serviceResponse = (
  name: string,
  description: string,
): components['schemas']['ServiceOfferingResponse'] => ({
  id: '80c438da-245b-450a-8ad2-9677308bf4d8',
  user_id: '74a38621-ddf4-433a-bd92-a15e90532dbf',
  name,
  description,
  created_at: '2026-10-08T00:00:00Z',
  updated_at: '2026-10-08T00:00:00Z',
});
const serviceProps = {
  initial: { name: 'Advisory', description: 'Launch support' },
  existing: true,
  save: vi.fn(),
  refreshSaved: vi.fn(),
  afterSave: vi.fn(),
};

describe('configuration drafts', () => {
  it('keeps its one-time initialization across prop refreshes and cancel restores its baseline', async () => {
    const wrapper = mount(ServiceOfferingForm, {
      props: serviceProps,
      global: { plugins: [PrimeVue] },
    });
    await wrapper.setProps({ initial: { name: 'Background value', description: 'Refreshed' } });
    await wrapper.get('button[type="button"]').trigger('click');
    expect((wrapper.get('#offering-name').element as HTMLInputElement).value).toBe('Advisory');
  });

  it('pauses an uncertain save until a successful refresh, keeps the draft, then cancels to refreshed values', async () => {
    const save = vi.fn().mockRejectedValue(new TypeError('network disconnected'));
    const refreshSaved = vi
      .fn()
      .mockResolvedValue(serviceResponse('Saved server name', 'Saved description'));
    const wrapper = mount(ServiceOfferingForm, {
      props: { ...serviceProps, save, refreshSaved },
      global: { plugins: [PrimeVue] },
    });
    await wrapper.get('#offering-name').setValue('My unsent draft');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('outcome is uncertain');
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect((wrapper.get('#offering-name').element as HTMLInputElement).value).toBe(
      'My unsent draft',
    );
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Cancel')
      ?.trigger('click');
    expect((wrapper.get('#offering-name').element as HTMLInputElement).value).toBe(
      'Saved server name',
    );
    expect(save).toHaveBeenCalledOnce();
  });

  it('shows nested ICP validation beside its row and preserves the submitted criteria', async () => {
    const save = vi
      .fn()
      .mockRejectedValue(
        new ApiError(422, 'request_failed', 'Check the highlighted fields.', [
          { path: ['industries', 0, 'name'], message: 'Industry is invalid.' },
        ]),
      );
    const wrapper = mount(IdealClientProfileForm, {
      props: {
        initial: {
          name: 'SaaS',
          industries: [{ name: 'SaaS' }],
          company_sizes: [],
          geographies: [],
          exclusions: [],
        },
        existing: true,
        save,
        refreshSaved: vi.fn(),
        afterSave: vi.fn(),
      },
      global: {
        plugins: [PrimeVue, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      },
    });
    await wrapper.get('#icp-name').setValue('Changed ICP');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Industry is invalid.');
    expect(wrapper.find('.p-chip-label').text()).toContain('SaaS');
    expect(save).toHaveBeenCalledWith(
      {
        name: 'Changed ICP',
        industries: [{ name: 'SaaS' }],
        company_sizes: [],
        geographies: [],
        exclusions: [],
      },
      { name: 'Changed ICP' },
    );
  });
});
