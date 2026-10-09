import { describe, expect, it } from 'vitest';
import type { components } from '@/api/generated/schema';
import {
  formatPipelineDuration,
  formatPipelineTime,
} from '@/features/pipeline/formatting/formatPipelineTime';
import { formatPipelineMetric } from '@/features/pipeline/formatting/formatPipelineMetric';
import {
  validateInvocationId,
  validatePipelineQuery,
} from '@/features/pipeline/navigation/validatePipelineQuery';

describe('pipeline display and navigation contracts', () => {
  it('keeps unknown metrics unknown and formats times without treating duration as progress', () => {
    const unknown: components['schemas']['MetricResponse'] = {
      kind: 'rows_written',
      unit: 'rows',
      value: null,
    };
    const known: components['schemas']['MetricResponse'] = {
      kind: 'rows_written',
      unit: 'rows',
      value: 1250,
    };
    expect(formatPipelineMetric(unknown)).toEqual({ label: 'Rows written', value: 'Unknown' });
    expect(formatPipelineMetric(known).value).toContain('1,250 rows');
    expect(formatPipelineTime('2026-10-09T10:00:00Z')).not.toBe('Unknown');
    expect(formatPipelineDuration('2026-10-09T10:00:00Z', null)).toBe('In progress');
    expect(formatPipelineDuration(null, null)).toBe('Not started');
  });

  it('validates UUID links and resets invalid history and stage query values', () => {
    expect(validateInvocationId('6ec48cf0-1632-4f3d-9ed3-68dc71af4429')).toBe(true);
    expect(validateInvocationId('not-an-id')).toBe(false);
    expect(validatePipelineQuery({ stage: 'unsupported', state: 'running', offset: '-5' })).toEqual(
      {
        stage: 'bronze',
        state: 'running',
        offset: 0,
      },
    );
    expect(
      validatePipelineQuery({ stage: 'gold', state: 'anything', offset: '9007199254740992' }),
    ).toEqual({
      stage: 'gold',
      offset: 0,
    });
  });
});
