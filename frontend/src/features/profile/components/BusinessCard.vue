<script setup lang="ts">
import { computed } from 'vue';
import { Building2, Globe, MapPin, Pencil } from '@lucide/vue';
import type { BusinessProfile } from '../models/businessProfile';
import { websiteLabel, websiteUrl } from '../lib/profileFormatting';

const props = defineProps<{
  business: BusinessProfile;
}>();
defineEmits<{ edit: [] }>();

const displayName = computed(() => props.business.name || 'Your business');
const link = computed(() => websiteUrl(props.business.website ?? ''));
</script>

<template>
  <section class="business-card" aria-label="Your business">
    <div class="card-header">
      <span class="logo" aria-hidden="true">
        <template v-if="business.name">{{ business.name.charAt(0) }}</template>
        <Building2 v-else :size="32" />
      </span>
      <div class="card-title">
        <h2 :class="{ 'is-empty': !business.name }">{{ displayName }}</h2>
        <p>{{ business.tagline || 'Add a short description of your business.' }}</p>
      </div>
      <button
        type="button"
        class="card-edit"
        aria-label="Edit business details"
        @click="$emit('edit')"
      >
        <Pencil :size="16" aria-hidden="true" />
        <span>Edit details</span>
      </button>
    </div>
    <ul v-if="business.location || link" class="card-facts">
      <li v-if="business.location">
        <MapPin :size="16" aria-hidden="true" />{{ business.location }}
      </li>
      <li v-if="link" class="card-link">
        <Globe :size="16" aria-hidden="true" />
        <a :href="link" target="_blank" rel="noopener noreferrer">{{
          websiteLabel(business.website ?? '')
        }}</a>
      </li>
    </ul>
    <ul v-if="business.capabilities?.length" class="capabilities" aria-label="Capabilities">
      <li v-for="capability in business.capabilities" :key="capability.name">
        {{ capability.name }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.business-card {
  display: grid;
  gap: var(--space-5);
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface-muted);
}
.card-edit {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--space-2);
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.card-edit:hover {
  border-color: var(--color-text-muted);
  background: var(--color-surface-muted);
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
.capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.capabilities li {
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
@media (max-width: 32rem) {
  .card-header {
    align-items: flex-start;
    flex-wrap: wrap;
  }
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
