import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import ExperienceRows from '../../../src/features/configuration/professional-profile/components/ExperienceRows.vue';
import SkillRows from '../../../src/features/configuration/professional-profile/components/SkillRows.vue';

describe('professional profile collection controls', () => {
  it('shows Present for a saved current experience without silently changing its draft', async () => {
    const wrapper = mount(ExperienceRows, {
      global: { plugins: [PrimeVue] },
      props: {
        modelValue: [
          {
            organization: 'Example',
            role: 'Engineer',
            summary: '',
            start_month: '2020-01',
            end_month: '2021-01',
            is_current: true,
          },
        ],
      },
    });
    const endMonthInput = wrapper.get('#experience-end-0');
    expect((endMonthInput.element as HTMLInputElement).value).toBe('Present');
    expect((endMonthInput.element as HTMLInputElement).disabled).toBe(true);
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });

  it('preserves duplicates and order when adding a skill', async () => {
    const wrapper = mount(SkillRows, {
      global: { plugins: [PrimeVue] },
      props: { modelValue: [{ name: 'Python' }, { name: 'Python' }] },
    });
    await wrapper.get('button[aria-label="Add skill"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toEqual([
      { name: 'Python' },
      { name: 'Python' },
      { name: '' },
    ]);
  });
});
