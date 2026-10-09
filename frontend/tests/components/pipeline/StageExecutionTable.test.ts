import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import type { components } from '@/api/generated/schema';
import StageExecutionTable from '@/features/pipeline/components/StageExecutionTable.vue';
import InvocationSummary from '@/features/pipeline/components/InvocationSummary.vue';

type Stage = components['schemas']['StageExecutionResponse'];
type Source = components['schemas']['SourceExecutionResponse'];
type Invocation = components['schemas']['InvocationDetailResponse'];

const stages: Stage[] = [
  {
    name: 'ingestion',
    order: 0,
    dependencies: [],
    state: 'succeeded',
    job_run_id: 'parent-one',
    started_at: '2026-10-09T09:00:00Z',
    finished_at: '2026-10-09T09:01:00Z',
    metrics: [{ kind: 'failed_sources', unit: 'sources', value: null }],
  },
  {
    name: 'ingestion.eu_startups',
    order: 1,
    dependencies: [],
    state: 'skipped',
    skip_reason: 'Dependency not succeeded: ingestion',
    metrics: [],
  },
];
const ingestionStage = stages[0];
const euStartupsStage = stages[1];
if (!ingestionStage || !euStartupsStage) throw new Error('Stage fixtures are incomplete.');

const sources: Source[] = [
  {
    name: 'hn',
    job_run_id: 'child-one',
    parent_job_run_id: 'parent-one',
    state: 'succeeded',
    started_at: '2026-10-09T09:00:00Z',
    finished_at: '2026-10-09T09:00:30Z',
    safe_error_code: null,
    metrics: [{ kind: 'rows_written', unit: 'rows', value: 14 }],
  },
  {
    name: 'yc',
    job_run_id: 'child-two',
    parent_job_run_id: 'other-parent',
    state: 'running',
    started_at: '2026-10-09T09:00:00Z',
    finished_at: null,
    safe_error_code: null,
    metrics: [],
  },
];

describe('pipeline stage views', () => {
  it('groups source jobs by explicit parent and distinguishes unknown, skipped, and active progress', () => {
    const wrapper = mount(StageExecutionTable, { props: { stages, sources, group: 'source' } });

    expect(wrapper.text()).toContain('hn');
    expect(wrapper.text()).not.toContain('yc');
    expect(wrapper.text()).toContain('Unknown');
    expect(wrapper.text()).toContain('Skipped: Dependency not succeeded: ingestion');
    expect(wrapper.find('progress').exists()).toBe(false);

    const silver = mount(StageExecutionTable, {
      props: {
        stages: [
          { ...euStartupsStage, name: 'silver.manual_review', state: 'not_executed' },
          { ...euStartupsStage, name: 'silver.signal_resolution', state: 'interrupted' },
        ],
        sources: [],
        group: 'silver',
      },
    });
    expect(silver.text()).toContain('silver.manual_review');
    expect(silver.text()).toContain('Not executed after interruption.');
    expect(silver.text()).toContain('Interrupted when execution stopped');
    expect(silver.text()).toContain('Manual review queueing is part of Silver.');
    expect(silver.find('button').exists()).toBe(false);

    const active = mount(StageExecutionTable, {
      props: {
        stages: [{ ...ingestionStage, state: 'running' }],
        sources,
        group: 'source',
      },
    });
    expect(active.find('progress').exists()).toBe(true);
    expect(active.find('progress').attributes('value')).toBeUndefined();
  });

  it('counts only succeeded, failed, and skipped stages as finished', () => {
    const invocation: Invocation = {
      id: '6ec48cf0-1632-4f3d-9ed3-68dc71af4429',
      request_id: '7ec48cf0-1632-4f3d-9ed3-68dc71af4429',
      requester_account_id: '8ec48cf0-1632-4f3d-9ed3-68dc71af4429',
      state: 'running',
      tracking_state: 'stale',
      requested_at: '2026-10-09T09:00:00Z',
      started_at: '2026-10-09T09:00:02Z',
      finished_at: null,
      heartbeat_at: '2026-10-09T09:00:05Z',
      safe_error_code: null,
      stages: [
        { ...ingestionStage, state: 'succeeded' },
        { ...euStartupsStage, state: 'failed' },
        { ...euStartupsStage, name: 'silver.hn_staging', state: 'skipped' },
        { ...euStartupsStage, name: 'gold.company', state: 'running' },
        { ...euStartupsStage, name: 'gold.company_signal', state: 'interrupted' },
        { ...euStartupsStage, name: 'silver.manual_review', state: 'not_executed' },
      ],
      sources,
    };
    const wrapper = mount(InvocationSummary, { props: { invocation } });
    expect(wrapper.text()).toContain('3 of 9 stages finished');
    expect(wrapper.text()).toContain('Failed stages');
    expect(wrapper.text()).toContain('Dependency skips');
    expect(wrapper.text()).toContain('Tracking is stale.');
  });
});
