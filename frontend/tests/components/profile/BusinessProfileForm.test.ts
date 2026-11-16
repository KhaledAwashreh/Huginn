import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import BusinessProfileForm from '@/features/profile/components/BusinessProfileForm.vue';
import type { BusinessProfile } from '@/features/profile/models/businessProfile';

const state = vi.hoisted(() => ({
  save: vi.fn(),
  refetch: vi.fn(),
}));

vi.mock('@/features/profile/composables/useBusinessProfile', () => ({
  useBusinessProfile: () => ({
    business: { refetch: state.refetch },
    save: { mutateAsync: state.save, isPending: { value: false } },
  }),
}));

const profile: BusinessProfile = {
  id: 'business-1',
  owner_user_id: 'user-1',
  name: null,
  tagline: null,
  website: null,
  location: null,
  description: null,
  capabilities: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};
const global = {
  plugins: [PrimeVue],
  stubs: { Dialog: { props: ['visible'], template: '<div v-if="visible"><slot /></div>' } },
};

beforeEach(() => {
  state.save.mockReset();
  state.refetch.mockReset();
});

it('patches only edited Business fields and closes after the server confirms the same identity', async () => {
  state.save.mockResolvedValue({ ...profile, description: 'Product strategy for small teams.' });
  const wrapper = mount(BusinessProfileForm, {
    props: { visible: true, profile },
    global,
  });
  await wrapper.get('#business-description').setValue('Product strategy for small teams.');
  await wrapper.get('#business-capabilities').setValue('Research\nProduct strategy');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(state.save).toHaveBeenCalledWith({
    description: 'Product strategy for small teams.',
    capabilities: [{ name: 'Research' }, { name: 'Product strategy' }],
  });
  expect(wrapper.emitted('update:visible')).toEqual([[false]]);
});

it('blocks unsafe website values before they reach the API', async () => {
  const wrapper = mount(BusinessProfileForm, {
    props: { visible: true, profile },
    global,
  });
  await wrapper.get('#business-website').setValue('javascript:alert(1)');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(state.save).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain('valid HTTP or HTTPS website address');
});

it('keeps an uncertain draft and adopts untouched fields from the exact Business refresh', async () => {
  state.save.mockRejectedValueOnce(new TypeError('the PATCH response was lost'));
  state.save.mockResolvedValueOnce({
    ...profile,
    name: 'A concurrent Business update',
    description: 'Our retained draft.',
  });
  state.refetch.mockResolvedValue({
    isError: false,
    data: { ...profile, name: 'A concurrent Business update' },
  });
  const wrapper = mount(BusinessProfileForm, {
    props: { visible: true, profile },
    global,
  });
  await wrapper.get('#business-description').setValue('Our retained draft.');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('save outcome is uncertain');
  expect((wrapper.get('#business-name').element as HTMLInputElement).value).toBe('');

  await wrapper.get('button[aria-label="Refresh saved data"]').trigger('click');
  await flushPromises();

  expect(state.refetch).toHaveBeenCalledOnce();
  expect((wrapper.get('#business-name').element as HTMLInputElement).value).toBe(
    'A concurrent Business update',
  );
  expect((wrapper.get('#business-description').element as HTMLTextAreaElement).value).toBe(
    'Our retained draft.',
  );
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(state.save).toHaveBeenNthCalledWith(2, { description: 'Our retained draft.' });
  expect(wrapper.emitted('update:visible')).toEqual([[false]]);
});

it('does not adopt a different owner response during an uncertain refresh', async () => {
  state.save.mockRejectedValueOnce(new TypeError('the PATCH response was lost'));
  state.refetch.mockResolvedValue({
    isError: false,
    data: { ...profile, id: 'other-business', owner_user_id: 'other-user', name: 'Other owner' },
  });
  const wrapper = mount(BusinessProfileForm, {
    props: { visible: true, profile },
    global,
  });
  await wrapper.get('#business-description').setValue('Draft stays local.');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  await wrapper.get('button[aria-label="Refresh saved data"]').trigger('click');
  await flushPromises();

  expect(wrapper.text()).toContain('could not be confirmed');
  expect((wrapper.get('#business-name').element as HTMLInputElement).value).toBe('');
  expect((wrapper.get('#business-description').element as HTMLTextAreaElement).value).toBe(
    'Draft stays local.',
  );
  expect((wrapper.get('button[type="submit"]').element as HTMLButtonElement).disabled).toBe(true);
});
