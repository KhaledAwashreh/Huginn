<script setup lang="ts">
import { RouterLink } from 'vue-router';
import type { RecommendationBatch } from '../models/recommendation';
import type { RecommendationFeedback } from '../models/recommendationFeedback';
import RecommendationFeedbackForm from './RecommendationFeedbackForm.vue';
import { companyWebsiteUrl, safeSourceUrl } from '../../matches/lib/externalCompanyUrl';
defineProps<{
  batch: RecommendationBatch;
  feedback: RecommendationFeedback[];
  feedbackAvailable: boolean;
}>();
const emit = defineEmits<{ saved: [RecommendationFeedback]; dirty: [string, boolean] }>();
const labels = {
  service_fit: 'Service fit',
  business_context: 'Business context',
  company_preferences: 'Company preferences',
  timing: 'Timing',
};
</script>
<template>
  <ol class="ranked-list" aria-label="Ranked research recommendations">
    <li v-for="(item, index) in batch.items" :key="item.id" class="recommendation-row">
      <div class="row-heading">
        <span class="rank">{{ index + 1 }}.</span>
        <div>
          <h2>
            <a
              v-if="companyWebsiteUrl(item.company.domain)"
              :href="companyWebsiteUrl(item.company.domain)!"
              target="_blank"
              rel="noopener noreferrer"
              >{{ item.company.name }}</a
            ><template v-else>{{ item.company.name }}</template>
          </h2>
          <span class="domain">{{ item.company.domain }}</span>
        </div>
        <div class="score">
          <strong>{{ item.score }} relevance</strong><span>{{ item.confidence }} confidence</span>
        </div>
      </div>
      <p>{{ item.rationale }}</p>
      <div v-for="strategy in item.strategies ?? []" :key="strategy.id">
        <RouterLink :to="{ path: '/recommendations', query: { strategy: strategy.id } }">{{
          strategy.name
        }}</RouterLink>
        · {{ strategy.offering }}
        <p v-if="strategy.rationale">{{ strategy.score }} relevance · {{ strategy.rationale }}</p>
        <blockquote
          v-for="(evidence, evidenceIndex) in strategy.evidence ?? []"
          :key="evidenceIndex"
        >
          {{ evidence.quote }}
          <a
            v-if="safeSourceUrl(evidence.source_url)"
            :href="safeSourceUrl(evidence.source_url)!"
            target="_blank"
            rel="noopener noreferrer"
            >Source for this strategy</a
          >
        </blockquote>
      </div>
      <p v-if="Object.values(item.icp_fit ?? {}).includes('unknown')">
        Some ICP information is unverified. Review the assessment details before outreach.
      </p>
      <details>
        <summary>Assessment, evidence and feedback for {{ item.company.name }}</summary>
        <div class="details-content">
          <section aria-label="Company context at assessment">
            <h3>Company context at assessment</h3>
            <p>These attributes were recorded when this assessment was generated.</p>
            <dl>
              <div>
                <dt>Country</dt>
                <dd>{{ item.company.country || 'Unknown' }}</dd>
              </div>
              <div>
                <dt>Business sectors</dt>
                <dd>
                  {{
                    item.company.business_sector?.length
                      ? item.company.business_sector.join(', ')
                      : 'Unknown'
                  }}
                </dd>
              </div>
              <div>
                <dt>Company size</dt>
                <dd>{{ item.company.company_scale || 'Unknown' }}</dd>
              </div>
            </dl>
          </section>
          <section>
            <h3>Assessment breakdown</h3>
            <p>
              {{
                item.selection_type === 'exploration'
                  ? 'Included to explore a less certain fit.'
                  : 'Included for its assessed relevance.'
              }}
            </p>
            <dl>
              <div v-for="(value, key) in item.breakdown" :key="key">
                <dt>{{ labels[key] }}</dt>
                <dd>{{ value }}</dd>
              </div>
            </dl>
            <h3>What is still unknown</h3>
            <ul v-if="item.unknowns.length">
              <li v-for="unknown in item.unknowns" :key="unknown">{{ unknown }}</li>
            </ul>
            <p v-else>No additional unknowns were recorded. Confirm fit before outreach.</p>
          </section>
          <section>
            <h3>Source evidence</h3>
            <p v-if="!item.evidence.length">No source excerpts are available.</p>
            <figure v-for="(evidence, i) in item.evidence" :key="i">
              <blockquote>{{ evidence.quote }}</blockquote>
              <figcaption>
                <a
                  v-if="safeSourceUrl(evidence.source_url)"
                  :href="safeSourceUrl(evidence.source_url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  >Open source</a
                ><span v-else>Source link unavailable</span>
                <p v-if="evidence.occurred_at">
                  Source date:
                  <time :datetime="evidence.occurred_at">{{
                    new Date(evidence.occurred_at).toLocaleString()
                  }}</time>
                </p>
                <p v-else>Source date unknown</p>
                <p v-if="evidence.observed_at">
                  Observed:
                  <time :datetime="evidence.observed_at">{{
                    new Date(evidence.observed_at).toLocaleString()
                  }}</time>
                </p>
              </figcaption>
            </figure>
          </section>
          <RecommendationFeedbackForm
            :batch-id="batch.id"
            :recommendation-id="item.id"
            :history="
              feedback.filter(
                (entry) => entry.batch_id === batch.id && entry.recommendation_id === item.id,
              )
            "
            @saved="emit('saved', $event)"
            @dirty="emit('dirty', item.id, $event)"
          />
          <p v-if="!feedbackAvailable">
            Feedback history is not yet available. New entries can still be saved.
          </p>
        </div>
      </details>
    </li>
  </ol>
</template>
<style scoped>
.ranked-list {
  list-style: none;
  padding: 0;
  margin: 0;
  border-top: 1px solid var(--color-border);
}
.recommendation-row {
  padding: var(--space-5) 0;
  border-bottom: 1px solid var(--color-border);
  overflow-wrap: anywhere;
}
.row-heading {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
  flex-wrap: wrap;
}
h2 {
  font-size: 1.2rem;
  margin: 0;
}
.rank {
  font-weight: 600;
}
.domain {
  color: var(--color-text-muted);
}
.score {
  margin-left: auto;
  display: grid;
  text-align: right;
  font-size: 0.875rem;
}
summary {
  cursor: pointer;
  color: var(--color-primary);
  padding: var(--space-2) 0;
  font-weight: 600;
}
.details-content {
  display: grid;
  gap: var(--space-5);
  padding: var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
}
figure {
  margin: var(--space-4) 0;
}
blockquote {
  margin: 0;
  padding-left: var(--space-4);
  border-left: 3px solid var(--color-border);
  white-space: pre-wrap;
}
figcaption {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}
dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3);
}
dl div {
  border-bottom: 1px solid var(--color-border);
}
dd {
  margin: 0;
  font-weight: 600;
}
</style>
