<script setup lang="ts">
import { RouterLink } from 'vue-router';
import type { UserMatch } from '../api/listMatches';
import { useMatchReactions } from '../composables/useMatchReactions';
import { matchDayLabel } from '../lib/matchDayLabel';
import MatchReactionActions from './MatchReactionActions.vue';

defineProps<{
  items: UserMatch[];
  fetching?: boolean;
}>();
const { reactionFor } = useMatchReactions();

// Placeholder logo: the company's initial on a colour derived from its name.
function logoHue(name: string): number {
  let hash = 0;
  for (const character of name) hash = (hash * 31 + character.charCodeAt(0)) % 360;
  return hash;
}
</script>

<template>
  <section class="match-grid-section" data-testid="match-list" :aria-busy="Boolean(fetching)">
    <p v-if="fetching" role="status" class="refreshing">Refreshing matches…</p>
    <ul class="match-grid">
      <li
        v-for="match in items"
        :key="match.id"
        :class="['match-tile', { 'match-tile--rejected': reactionFor(match.id)?.kind === 'down' }]"
        data-testid="match-row"
      >
        <div class="tile-top">
          <span
            class="logo"
            :style="{ backgroundColor: `hsl(${logoHue(match.company.name)} 45% 32%)` }"
            aria-hidden="true"
            >{{ match.company.name.charAt(0) }}</span
          >
          <span v-if="reactionFor(match.id)?.kind === 'up'" class="tile-tag tile-tag--prospect"
            >Prospect</span
          >
          <span v-else-if="reactionFor(match.id)?.kind === 'down'" class="tile-tag">Not a fit</span>
          <span v-else-if="match.status === 'new'" class="tile-tag tile-tag--new">New</span>
        </div>
        <h2>
          <RouterLink :to="{ name: 'match-detail', params: { id: match.id } }">{{
            match.company.name
          }}</RouterLink>
        </h2>
        <p class="tile-meta">{{ match.company.domain }}</p>
        <p class="tile-meta">
          {{
            [match.company.business_sector?.join(', '), match.company.country]
              .filter(Boolean)
              .join(' · ') || 'No details yet'
          }}
        </p>
        <div class="tile-bottom">
          <time :datetime="match.created_at">{{ matchDayLabel(new Date(match.created_at)) }}</time>
          <MatchReactionActions :match="match" />
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.match-grid-section {
  display: grid;
  gap: var(--space-6);
  min-width: 0;
}
.match-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 16rem), 1fr));
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.match-tile {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.match-tile:hover {
  border-color: var(--color-text-muted);
}
.match-tile--rejected {
  background: var(--color-surface-muted);
}
.tile-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.logo {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-control);
  color: #ffffff;
  font-size: 1.25rem;
  font-weight: 650;
}
.tile-tag {
  padding: 2px var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}
.tile-tag--new {
  color: var(--color-text);
}
.tile-tag--prospect {
  border-color: var(--color-success-border);
  background: var(--color-success-surface);
  color: var(--color-success-text);
}
h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}
h2 a {
  color: var(--color-text);
  text-decoration: none;
}
/* The whole tile opens the match; the reaction buttons sit above this layer. */
h2 a::after {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-card);
  content: '';
}
h2 a:focus-visible::after {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
.tile-meta {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}
.tile-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: auto;
  padding-top: var(--space-3);
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
.tile-bottom :deep(.match-reactions) {
  position: relative;
  z-index: 1;
}
.refreshing {
  margin: 0;
  color: var(--color-text-muted);
}
</style>
