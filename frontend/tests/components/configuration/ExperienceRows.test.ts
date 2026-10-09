import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import PrimeVue from 'primevue/config';
import ExperienceRows from '../../../src/features/configuration/professional-profile/components/ExperienceRows.vue';
import type { ExperienceDraft } from '../../../src/features/configuration/professional-profile/forms/professionalProfileDraft';

const row = (overrides: Partial<ExperienceDraft> = {}): ExperienceDraft => ({
  organization: 'Example Co',
  role: 'Engineer',
  summary: '',
  start_month: '2020-01',
  end_month: '2023-01',
  is_current: false,
  ...overrides,
});

describe('experience rows', () => {
  it('clears the end month and shows disabled Present for a current role', async () => {
    const wrapper = mount(ExperienceRows, {
      props: { modelValue: [row(), row({ organization: 'Another Co', end_month: '' })] },
      global: { plugins: [PrimeVue] },
    });

    await wrapper
      .get('[aria-labelledby="experience-heading-0"] input[type="checkbox"]')
      .setValue(true);

    const updated = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as ExperienceDraft[];
    expect(updated[0]).toMatchObject({ is_current: true, end_month: '' });
    await wrapper.setProps({ modelValue: updated });

    const endMonth = wrapper.get('#experience-end-0').element as HTMLInputElement;
    expect(endMonth.value).toBe('Present');
    expect(endMonth.disabled).toBe(true);
    expect(
      (
        wrapper.get('[aria-labelledby="experience-heading-1"] input[type="checkbox"]')
          .element as HTMLInputElement
      ).disabled,
    ).toBe(true);

    await wrapper
      .get('[aria-labelledby="experience-heading-0"] input[type="checkbox"]')
      .setValue(false);
    const unchecked = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as ExperienceDraft[];
    await wrapper.setProps({ modelValue: unchecked });
    expect(
      (
        wrapper.get('[aria-labelledby="experience-heading-1"] input[type="checkbox"]')
          .element as HTMLInputElement
      ).disabled,
    ).toBe(false);
  });
});
