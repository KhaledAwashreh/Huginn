import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import { h } from 'vue';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import type { components } from '../../../src/api/generated/schema';
import { ApiError } from '../../../src/api/apiError';
import ProfessionalProfileForm from '../../../src/features/configuration/professional-profile/components/ProfessionalProfileForm.vue';

const state = vi.hoisted(() => ({ refetch: vi.fn(), save: vi.fn() }));
vi.mock(
  '../../../src/features/configuration/professional-profile/composables/useProfessionalProfile',
  () => ({
    useProfessionalProfile: () => ({
      profile: { refetch: state.refetch },
      save: { mutateAsync: state.save, isPending: { value: false } },
    }),
  }),
);

type Profile = components['schemas']['ProfessionalProfileResponse'];
const profile: Profile = {
  id: 'profile-1',
  user_id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  headline: 'Engineer',
  professional_summary: null,
  skills: [{ name: 'Python' }],
  experience: [],
  previous_projects: [],
};
async function renderProfile() {
  const routeComponent = { setup: () => () => h(ProfessionalProfileForm, { profile }) };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/profile', component: routeComponent }],
  });
  await router.push('/profile');
  const wrapper = mount(RouterView, { global: { plugins: [router, PrimeVue] } });
  await flushPromises();
  return wrapper;
}
afterEach(() => vi.clearAllMocks());

describe('professional profile form', () => {
  it('shows nested 422 feedback at the matching repeated field', async () => {
    state.save.mockRejectedValueOnce(
      new ApiError(422, 'request_failed', 'Check the highlighted fields.', [
        { path: ['skills', 0, 'name'], message: 'Skill name is invalid.' },
      ]),
    );
    const wrapper = await renderProfile();
    await wrapper.get('#profile-headline').setValue('Senior engineer');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Skill name is invalid.');
  });

  it('sends an empty array to clear skills and accepts the server response', async () => {
    state.save.mockResolvedValueOnce({ ...profile, skills: [], headline: 'Engineer' });
    const wrapper = await renderProfile();
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Remove skill')
      ?.trigger('click');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(state.save).toHaveBeenCalledWith({ skills: [] });
    expect(wrapper.text()).not.toContain('Skill 1');
  });
});
