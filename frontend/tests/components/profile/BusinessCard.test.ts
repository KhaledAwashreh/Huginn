import { mount } from '@vue/test-utils';
import { expect, it } from 'vitest';
import BusinessCard from '@/features/profile/components/BusinessCard.vue';
import type { BusinessProfile } from '@/features/profile/models/businessProfile';

const profile: BusinessProfile = {
  id: 'business-1',
  owner_user_id: 'user-1',
  name: null,
  tagline: null,
  website: 'javascript:alert(1)',
  location: 'Amman',
  description: null,
  capabilities: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

it('never renders an unsafe saved website as a link', () => {
  const wrapper = mount(BusinessCard, { props: { business: profile } });
  expect(wrapper.find('a').exists()).toBe(false);
  expect(wrapper.get('[aria-label="Your business"]').text()).toContain('Amman');
});

it('offers an explicit accessible Business edit control', async () => {
  const wrapper = mount(BusinessCard, { props: { business: profile } });
  await wrapper.get('button[aria-label="Edit business details"]').trigger('click');
  expect(wrapper.emitted('edit')).toHaveLength(1);
});
