<script setup lang="ts">
import { computed, useId } from 'vue';
import { useSession } from '../../session/composables/useSession';
import { companyWebsiteUrl } from '../../../shared/lib/externalCompanyUrl';
import RecommendationAssessment from './RecommendationAssessment.vue';
import {
  record,
  relevanceScore,
  retainedEvidence,
  strategyName,
  text,
} from '../models/assessmentEvidence';
import type { RecommendationView } from '../models/prospecting';

const props = defineProps<{ recommendation: RecommendationView; strategyId?: string }>();
const headingId = useId();
const session = useSession();
const simpleDiscovery = computed(() => session.context.value?.simple_discovery_enabled === true);
const assessment = computed(() => {
  const current = props.recommendation.assessment;
  if (!current || !props.strategyId) return current;
  return {
    ...current,
    strategy_assessments: current.strategy_assessments.filter(
      (item) => item.strategy_id === props.strategyId,
    ),
  };
});
const scores = computed(() =>
  (assessment.value?.strategy_assessments ?? []).flatMap((item) => {
    const score = relevanceScore(item);
    return score === null
      ? []
      : [
          {
            id: item.strategy_id,
            name: simpleDiscovery.value
              ? text(record(item.offering_snapshot).name) || 'Service offering'
              : strategyName(item),
            score,
          },
        ];
  }),
);
const signalCount = computed(() => {
  const current = assessment.value;
  if (!current) return 0;
  return new Set(
    current.strategy_assessments.flatMap((item) =>
      retainedEvidence(current, item).map(
        (source) => text(source.observation_id) ?? `${source.source_url}:${source.quote}`,
      ),
    ),
  ).size;
});
</script>

<template>
  <section
    class="recommendation-evidence"
    :aria-labelledby="headingId"
    :data-assessment-revision-id="recommendation.assessment?.id"
  >
    <details>
      <summary>
        <div class="company-heading">
          <div class="identity">
            <span class="company-initial" aria-hidden="true">{{
              recommendation.company.name.slice(0, 1)
            }}</span>
            <div>
              <h2 :id="headingId">{{ recommendation.company.name }}</h2>
              <span class="domain">{{ recommendation.company.domain }}</span>
            </div>
          </div>
          <div v-if="scores.length" class="scores" aria-label="Relevance">
            <p v-for="score in scores" :key="score.id" class="relevance-score">
              <span v-if="scores.length > 1">{{ score.name }}: </span>
              <span class="score-label">Relevance: </span><strong>{{ score.score }}</strong
              >/100
            </p>
          </div>
        </div>
        <p v-if="recommendation.company.description" class="description">
          {{ recommendation.company.description }}
        </p>
        <div class="preview-bottom">
          <span
            >{{ signalCount }} company {{ signalCount === 1 ? 'signal' : 'signals'
            }}<template v-if="recommendation.company.country">
              · {{ recommendation.company.country }}</template
            ></span
          >
          <span class="expand"
            ><span class="expand-closed">View company &amp; signals</span
            ><span class="expand-open">Hide details</span><span class="chevron" aria-hidden="true"
          /></span>
        </div>
      </summary>
      <div class="expanded">
        <section class="company-info" aria-label="Company info">
          <h3>Company info</h3>
          <p v-if="recommendation.company.description">{{ recommendation.company.description }}</p>
          <dl>
            <div v-if="recommendation.company.country">
              <dt>Country</dt>
              <dd>{{ recommendation.company.country }}</dd>
            </div>
            <div v-if="recommendation.company.business_sector?.length">
              <dt>Business sectors</dt>
              <dd>{{ recommendation.company.business_sector.join(', ') }}</dd>
            </div>
            <div v-if="recommendation.company.company_scale">
              <dt>Company scale</dt>
              <dd>{{ recommendation.company.company_scale }}</dd>
            </div>
            <div v-if="recommendation.company.company_status">
              <dt>Company status</dt>
              <dd>{{ recommendation.company.company_status }}</dd>
            </div>
          </dl>
          <a
            v-if="companyWebsiteUrl(recommendation.company.domain)"
            :href="companyWebsiteUrl(recommendation.company.domain) ?? undefined"
            target="_blank"
            rel="noopener noreferrer"
            >{{ recommendation.company.domain }}</a
          >
        </section>
        <RecommendationAssessment :assessment="assessment" signals-only />
      </div>
    </details>
  </section>
</template>

<style scoped>
.recommendation-evidence {
  min-width: 0;
}
summary {
  cursor: pointer;
  list-style: none;
  padding: var(--space-4) var(--space-5);
}
summary::-webkit-details-marker {
  display: none;
}
summary:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: -3px;
  border-radius: var(--radius-card);
}
.company-heading,
.identity,
.preview-bottom,
.expand {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
.company-heading,
.preview-bottom {
  justify-content: space-between;
}
.identity {
  min-width: 0;
}
.company-initial {
  display: grid;
  place-items: center;
  width: 2.3rem;
  height: 2.3rem;
  flex-shrink: 0;
  background: var(--color-surface-muted);
  color: var(--color-primary);
  border-radius: var(--radius-control);
  font-size: 1.2rem;
  font-weight: 700;
}
h2,
h3,
p {
  margin: 0;
}
h2 {
  font-size: 1.05rem;
  overflow-wrap: anywhere;
}
h3 {
  font-size: 0.95rem;
}
.domain,
.preview-bottom,
dt {
  color: var(--color-text-muted);
  font-size: 0.8rem;
}
.domain {
  overflow-wrap: anywhere;
}
.scores {
  flex-shrink: 0;
  color: var(--color-primary);
  text-align: right;
  font-size: 0.8rem;
}
.score-label {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.relevance-score strong {
  font-size: 0.95rem;
}
.description,
.preview-bottom {
  margin-top: var(--space-2);
  padding-left: 3.05rem;
}
.description {
  color: var(--color-text-muted);
  font-size: 0.875rem;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.preview-bottom {
  gap: var(--space-2);
}
.expand {
  color: var(--color-primary);
  font-weight: 600;
  gap: var(--space-2);
}
.chevron {
  width: 0.45rem;
  height: 0.45rem;
  border-right: 1.5px solid;
  border-bottom: 1.5px solid;
  transform: rotate(45deg);
  margin-top: -0.2rem;
  flex-shrink: 0;
}
.expand-open,
details[open] .expand-closed {
  display: none;
}
details[open] .expand-open {
  display: inline;
}
details[open] .chevron {
  transform: rotate(225deg);
  margin-top: 0.2rem;
}
.expanded {
  display: grid;
  gap: var(--space-5);
  padding: 0 var(--space-5) var(--space-5) calc(var(--space-5) + 3.05rem);
}
.company-info {
  display: grid;
  gap: var(--space-3);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-4);
  font-size: 0.875rem;
}
.company-info > p {
  overflow-wrap: anywhere;
}
dl {
  display: flex;
  gap: var(--space-3) var(--space-5);
  flex-wrap: wrap;
  margin: 0;
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
a {
  color: var(--color-primary);
  overflow-wrap: anywhere;
}
@media (max-width: 700px) {
  summary {
    padding: var(--space-4);
  }
  .company-heading {
    gap: var(--space-2);
    align-items: flex-start;
  }
  .description,
  .preview-bottom {
    padding-left: 0;
  }
  .preview-bottom {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .expanded {
    padding: 0 var(--space-4) var(--space-4);
  }
  .scores {
    max-width: 40%;
    white-space: normal;
    overflow-wrap: anywhere;
  }
}
</style>
