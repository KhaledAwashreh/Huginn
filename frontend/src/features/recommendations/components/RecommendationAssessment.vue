<script setup lang="ts">
import type { components } from '../../../api/generated/schema';
import { safeSourceUrl } from '../../../shared/lib/externalCompanyUrl';
import { record, retainedEvidence, strategyName, text } from '../models/assessmentEvidence';

defineProps<{
  assessment: components['schemas']['AssessmentRevisionResponse'] | null;
  evidenceState?: components['schemas']['RecommendationResponse']['evidence_state'];
  heading?: string;
}>();
const evidenceLabels: Record<
  components['schemas']['RecommendationResponse']['evidence_state'],
  string
> = {
  current: 'Current source evidence is available and unchanged from this assessment.',
  changed:
    'Current source evidence differs from this assessment. The original evidence is preserved here.',
  unavailable:
    'Current source evidence is unavailable. This assessment’s evidence remains available below.',
  not_assessed: 'Current source evidence has not been reassessed.',
};
function utc(value: string): string {
  return new Date(value).toLocaleString(undefined, { timeZone: 'UTC', timeZoneName: 'short' });
}
function safeSource(value: unknown): string | null {
  return typeof value === 'string' ? safeSourceUrl(value) : null;
}
</script>

<template>
  <section
    class="assessment-context"
    aria-label="Assessment rationale and evidence"
    :data-assessment-revision-id="assessment?.id"
  >
    <h3>{{ heading ?? 'Why this recommendation appeared' }}</h3>
    <p v-if="!assessment">No assessment revision is available for this record.</p>
    <p v-if="evidenceState" class="evidence-state">{{ evidenceLabels[evidenceState] }}</p>

    <template v-if="assessment">
      <article
        v-for="item in assessment.strategy_assessments"
        :key="item.strategy_id"
        class="strategy-assessment"
      >
        <h4 v-if="assessment.strategy_assessments.length > 1">{{ strategyName(item) }}</h4>
        <p>
          {{
            text(record(item.assessment_snapshot).rationale) ||
            'No rationale text was retained for this strategy assessment.'
          }}
        </p>
        <section class="source-evidence" :aria-label="`Evidence for ${strategyName(item)}`">
          <h5>Assessment-time source evidence</h5>
          <p v-if="!retainedEvidence(assessment, item).length">No source excerpts were retained.</p>
          <figure v-for="(source, index) in retainedEvidence(assessment, item)" :key="index">
            <blockquote>{{ text(source.quote) || 'Source excerpt unavailable.' }}</blockquote>
            <figcaption>
              <a
                v-if="text(source.source_url) && safeSource(source.source_url)"
                :href="safeSource(source.source_url) ?? undefined"
                target="_blank"
                rel="noopener noreferrer"
                >Open source</a
              ><span v-else>Source link unavailable</span>
              <time v-if="text(source.occurred_at)" :datetime="text(source.occurred_at)!">
                Source date: {{ utc(text(source.occurred_at)!) }}
              </time>
            </figcaption>
          </figure>
        </section>
        <details>
          <summary>Assessment-time company attributes</summary>
          <pre>{{
            JSON.stringify(record(record(item.assessment_snapshot).company_facts), null, 2)
          }}</pre>
        </details>
      </article>
    </template>
  </section>
</template>

<style scoped>
.assessment-context {
  display: grid;
  gap: var(--space-2);
}
h3,
h4,
h5,
p {
  margin-top: 0;
}
h3 {
  margin-bottom: var(--space-2);
  font-size: 1.05rem;
}
h4 {
  margin-bottom: var(--space-2);
}
h5 {
  margin-bottom: var(--space-1);
}
.evidence-state,
.offering {
  color: var(--color-text-muted);
}
.strategy-assessment {
  display: grid;
  gap: var(--space-2);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-3);
}
figure {
  margin: var(--space-2) 0;
}
blockquote {
  margin: 0;
  padding-left: var(--space-3);
  border-left: 3px solid var(--color-border);
  white-space: pre-wrap;
}
figcaption {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
a {
  color: var(--color-primary);
  overflow-wrap: anywhere;
}
pre {
  max-height: 18rem;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
