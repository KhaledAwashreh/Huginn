import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { expect, it, vi } from 'vitest';
import { reactive } from 'vue';
import type { IdealClientProfileDraft } from '@/features/configuration/ideal-client-profiles/forms/idealClientProfileDraft';
import IdealClientProfileForm from '@/features/configuration/ideal-client-profiles/components/IdealClientProfileForm.vue';

vi.mock(
  '@/features/configuration/ideal-client-profiles/composables/useConfigurationOptions',
  () => ({
    useConfigurationOptions: () => ({
      data: {
        value: { industries: [], countries: [], company_sizes: [] },
      },
      isPending: { value: false },
      isError: { value: false },
    }),
  }),
);

const initial: IdealClientProfileDraft = {
  name: '',
  industries: [],
  company_sizes: [],
  geographies: [],
  exclusions: [],
};

it('does not retry an uncertain create after a successful list refresh', async () => {
  const save = vi.fn().mockRejectedValue(new TypeError('network unavailable'));
  const wrapper = mount(IdealClientProfileForm, {
    props: {
      initial,
      existing: false,
      save,
      refreshSaved: async () => null,
      afterSave: vi.fn(),
    },
    global: { plugins: [PrimeVue] },
  });

  await wrapper.get('#icp-name').setValue('Second ICP');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('outcome is uncertain');
  expect(save).toHaveBeenCalledOnce();

  await wrapper.get('button[aria-label="Refresh saved data"]').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('create result is still uncertain');
  expect((wrapper.get('#icp-name').element as HTMLInputElement).value).toBe('Second ICP');
  expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
  await wrapper.get('form').trigger('submit');
  expect(save).toHaveBeenCalledOnce();
});

it('accepts an initial ICP containing reactive rows and preserves them through a save', async () => {
  const row = reactive({ name: 'Software' });
  const original = { ...initial, name: 'Existing ICP', industries: [row] };
  const save = vi.fn(async (draft: IdealClientProfileDraft) => ({
    ...draft,
    id: 'icp-1',
    business_id: 'business-1',
    created_at: '2026-11-01',
    updated_at: '2026-11-01',
  }));
  const wrapper = mount(IdealClientProfileForm, {
    props: {
      initial: original,
      existing: true,
      save,
      refreshSaved: async () => null,
      afterSave: vi.fn(),
    },
    global: { plugins: [PrimeVue] },
  });
  await wrapper.get('#icp-name').setValue('Updated ICP');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(save).toHaveBeenCalledOnce();
  const passed = save.mock.calls[0]?.[0];
  expect(structuredClone(passed)).toMatchObject({
    name: 'Updated ICP',
    industries: [{ name: 'Software' }],
  });
  expect(wrapper.text()).not.toContain('outcome is uncertain');
});
