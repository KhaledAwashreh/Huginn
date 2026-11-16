<script setup lang="ts">
import { companyWebsiteUrl } from '../../../shared/lib/externalCompanyUrl';
import RecommendationAssessment from './RecommendationAssessment.vue';
import type { RecommendationView } from '../models/prospecting';
import { computed, useId } from 'vue';

const props = defineProps<{ recommendation: RecommendationView }>();
const recommendation = computed(() => props.recommendation);
const headingId = useId();
const eligibilityLabels: Record<RecommendationView['current_eligibility'], string> = {
  historical: 'Resolved historical recommendation',
  blocked: 'Currently blocked by an independent decision or relationship',
  unavailable: 'Current evidence is unavailable',
  not_reassessed: 'Current evidence has not been reassessed',
};
function label(value: string): string {
  return value.replaceAll('_', ' ');
}
function utc(value: string): string {
  return new Date(value).toLocaleString(undefined, { timeZone: 'UTC', timeZoneName: 'short' });
}
</script>

<template>
  <section class="recommendation-evidence" :aria-labelledby="headingId">
    <header class="company-heading">
      <div>
        <h2 :id="headingId">{{ recommendation.company.name }}</h2>
        <a
          v-if="companyWebsiteUrl(recommendation.company.domain)"
          :href="companyWebsiteUrl(recommendation.company.domain) ?? undefined"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ recommendation.company.domain }}
        </a>
        <span v-else>{{ recommendation.company.domain }}</span>
      </div>
      <span class="eligibility">{{ eligibilityLabels[recommendation.current_eligibility] }}</span>
    </header>

    <section class="current-context" aria-label="Current company context">
      <h3>Current company context</h3>
      <p>
        These fields describe the company now. They are separate from the attributes and evidence
        captured when the shown assessment was made.
      </p>
      <dl>
        <div>
          <dt>Country</dt>
          <dd>{{ recommendation.company.country || 'Not available' }}</dd>
        </div>
        <div>
          <dt>Business sectors</dt>
          <dd>{{ recommendation.company.business_sector?.join(', ') || 'Not available' }}</dd>
        </div>
        <div>
          <dt>Company scale</dt>
          <dd>{{ recommendation.company.company_scale || 'Not available' }}</dd>
        </div>
        <div>
          <dt>Company status</dt>
          <dd>{{ recommendation.company.company_status || 'Not available' }}</dd>
        </div>
      </dl>
    </section>

    <RecommendationAssessment
      :assessment="recommendation.assessment"
      :evidence-state="recommendation.evidence_state"
    />

    <section
      v-if="recommendation.selection_blockers.length || recommendation.active_blocks.length"
      class="blockers"
      aria-label="Current independent blockers"
    >
      <h3>Current independent blockers</h3>
      <ul>
        <li v-for="blocker in recommendation.selection_blockers" :key="blocker">
          {{ label(blocker) }}
        </li>
      </ul>
      <ul>
        <li v-for="block in recommendation.active_blocks" :key="block.id">
          {{ label(block.kind) }}<span v-if="block.reason">: {{ block.reason }}</span>
          <time v-if="block.expires_at" :datetime="block.expires_at">
            through {{ utc(block.expires_at) }}</time
          >
          <span v-else-if="block.kind === 'pause'"> indefinitely</span>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.recommendation-evidence {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.company-heading {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
}
h2,
h3,
h4,
h5,
p {
  margin-top: 0;
}
h2 {
  margin-bottom: var(--space-1);
  font-size: 1.25rem;
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
a {
  color: var(--color-primary);
  overflow-wrap: anywhere;
}
.eligibility {
  color: var(--color-text-muted);
}
.current-context,
.blockers {
  display: grid;
  gap: var(--space-2);
}
.current-context > p {
  color: var(--color-text-muted);
}
dl {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin: 0;
}
dt {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
dd {
  margin: 0;
}
</style>
