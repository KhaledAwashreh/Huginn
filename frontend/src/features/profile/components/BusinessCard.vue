<script setup lang="ts">
import { computed } from 'vue';
import { Building2, Globe, MapPin, UsersRound } from '@lucide/vue';
import { awaitingBackendAttrs } from '../../../shared/availability/awaitingBackend';
import type { BusinessDetails } from '../composables/useBusinessDetails';
import { websiteLabel, websiteUrl } from '../lib/profileFormatting';

const props = defineProps<{
  business: BusinessDetails;
}>();
defineEmits<{ edit: [] }>();

const displayName = computed(() => props.business.name || 'Your business');
const link = computed(() => websiteUrl(props.business.website));
</script>

<template>
  <section class="business-card" aria-label="Your business">
    <button
      v-bind="awaitingBackendAttrs"
      type="button"
      class="card-edit"
      aria-label="Edit business details"
      @click="$emit('edit')"
    />
    <div class="card-header">
      <span class="logo" aria-hidden="true">
        <template v-if="business.name">{{ business.name.charAt(0) }}</template>
        <Building2 v-else :size="32" />
      </span>
      <div class="card-title">
        <h2 :class="{ 'is-empty': !business.name }">{{ displayName }}</h2>
        <p>{{ business.tagline || 'Business details are coming soon' }}</p>
      </div>
    </div>
    <ul v-if="business.location || business.practice || link" class="card-facts">
      <li v-if="business.location">
        <MapPin :size="16" aria-hidden="true" />{{ business.location }}
      </li>
      <li v-if="business.practice">
        <UsersRound :size="16" aria-hidden="true" />{{ business.practice }}
      </li>
      <li v-if="link" class="card-link">
        <Globe :size="16" aria-hidden="true" />
        <a :href="link" target="_blank" rel="noopener noreferrer">{{
          websiteLabel(business.website)
        }}</a>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.business-card {
  position: relative;
  display: grid;
  gap: var(--space-5);
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface-muted);
}
.business-card:has(.card-edit:not(:disabled)):hover {
  border-color: var(--color-text-muted);
}
.card-edit {
  position: absolute;
  inset: 0;
  border: 0;
  border-radius: 12px;
  background: transparent;
  cursor: pointer;
}
.card-edit:disabled {
  cursor: not-allowed;
}
.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.logo {
  flex: none;
  width: 72px;
  height: 72px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--color-primary);
  color: var(--color-surface);
  font-size: 2rem;
  font-weight: 650;
}
.card-title {
  min-width: 0;
}
h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
h2.is-empty {
  color: var(--color-text-muted);
}
.card-title p {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
}
.card-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-5);
  margin: 0;
  padding: 0;
  color: var(--color-text-muted);
  font-size: 0.9375rem;
  list-style: none;
}
.card-facts li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  overflow-wrap: anywhere;
}
/* Sits above the card's edit layer so the link still opens the site. */
.card-link {
  position: relative;
  z-index: 1;
}
.card-link a {
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  color: var(--color-text);
}
</style>
