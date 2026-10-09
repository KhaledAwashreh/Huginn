import type { components } from '../../../api/generated/schema';

type Metric = components['schemas']['MetricResponse'];

const LABELS: Record<string, string> = {
  rows_fetched: 'Rows fetched',
  rows_written: 'Rows written',
  records_seen: 'Records seen',
  records_written: 'Records written',
  companies_processed: 'Companies processed',
  companies_written: 'Companies written',
  companies_skipped: 'Companies skipped',
  sources_succeeded: 'Sources succeeded',
  sources_failed: 'Sources failed',
  failed_sources: 'Sources failed',
};

export function formatPipelineMetric(metric: Metric): { label: string; value: string } {
  const label = LABELS[metric.kind] ?? metric.kind.replaceAll('_', ' ');
  if (metric.value === null) return { label, value: 'Unknown' };
  const value = new Intl.NumberFormat().format(metric.value);
  return { label, value: metric.unit ? `${value} ${metric.unit}` : value };
}
