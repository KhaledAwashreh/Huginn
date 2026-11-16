import PrimeVue from 'primevue/config';
import { expect, it } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import IcpReferenceSelect from '@/features/configuration/discovery-strategies/components/IcpReferenceSelect.vue';

it('links ICP management to the approved Profile surface', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/profile', component: { template: '<h1>Profile</h1>' } },
      { path: '/strategies/new', component: { template: '<h1>Strategy</h1>' } },
    ],
  });
  await router.push('/strategies/new');
  const wrapper = mount(IcpReferenceSelect, {
    props: {
      modelValue: '',
      disabled: false,
      items: [],
      hasMore: false,
      loading: false,
      unavailable: false,
      error: '',
      feedback: '',
    },
    global: { plugins: [PrimeVue, router], stubs: { Select: true, Button: true } },
  });
  await flushPromises();

  const managementLink = wrapper.get('a');
  expect(managementLink.text()).toBe('Manage ICPs in Profile');
  expect(managementLink.attributes('href')).toBe('/profile');
});
