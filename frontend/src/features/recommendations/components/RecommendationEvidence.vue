<script setup lang="ts">
import { companyWebsiteUrl } from '../../../shared/lib/externalCompanyUrl';
import RecommendationAssessment from './RecommendationAssessment.vue';
import type { RecommendationView } from '../models/prospecting';
import { computed, useId } from 'vue';

const props = defineProps<{ recommendation: RecommendationView }>();
const recommendation = computed(() => props.recommendation);
const headingId = useId();
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
.current-context {
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
