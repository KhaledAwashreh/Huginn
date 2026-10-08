import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import EmptyState from '@/shared/ui/EmptyState.vue';
import ErrorState from '@/shared/ui/ErrorState.vue';
import FieldFeedback from '@/shared/ui/FieldFeedback.vue';
import LoadingState from '@/shared/ui/LoadingState.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import StatusLabel from '@/shared/ui/StatusLabel.vue';

describe('shared UI states', () => {
  it('renders a page title, optional description, and its action slot', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Account settings', description: 'Manage your profile.' },
      slots: { default: '<button type="button">Save changes</button>' },
    });

    expect(wrapper.get('h1').text()).toBe('Account settings');
    expect(wrapper.text()).toContain('Manage your profile.');
    expect(wrapper.get('button').text()).toBe('Save changes');
  });

  it('associates visible field guidance with its supplied description id', () => {
    const wrapper = mount(FieldFeedback, {
      props: { id: 'email-error', message: 'Enter a valid email address.' },
    });

    expect(wrapper.get('[role="alert"]').attributes('id')).toBe('email-error');
    expect(wrapper.text()).toBe('Enter a valid email address.');
  });

  it('does not render an empty field error', () => {
    const wrapper = mount(FieldFeedback);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it('announces loading and empty states with their supplied context', () => {
    const loading = mount(LoadingState, { props: { message: 'Loading strategies' } });
    const empty = mount(EmptyState, { props: { message: 'No strategies yet.' } });

    expect(loading.get('[role="status"]').text()).toContain('Loading strategies');
    expect(empty.text()).toContain('No strategies yet.');
  });

  it('keeps the retry action available in an announced error state', () => {
    const wrapper = mount(ErrorState, {
      props: { message: 'Could not load strategies.' },
      slots: { default: '<button type="button">Try again</button>' },
    });

    expect(wrapper.get('[role="alert"]').text()).toContain('Could not load strategies.');
    expect(wrapper.get('button').text()).toBe('Try again');
  });

  it('shows the status as text so color is never the only cue', () => {
    const wrapper = mount(StatusLabel, { props: { status: 'Paused' } });
    expect(wrapper.text()).toBe('Paused');
    expect(wrapper.get('[role="status"]').text()).toBe('Paused');
  });
});
