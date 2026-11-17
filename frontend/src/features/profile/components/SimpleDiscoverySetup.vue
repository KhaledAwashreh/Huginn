<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useQueryClient } from '@tanstack/vue-query';
import Button from 'primevue/button';
import { useSession } from '../../session/composables/useSession';
import { useActiveDiscoveryStrategies } from '../../configuration/discovery-strategies/composables/useActiveDiscoveryStrategies';
import { useStrategyReferences } from '../../configuration/discovery-strategies/composables/useStrategyReferences';
import { saveSingleDiscoveryConfiguration } from '../../configuration/discovery-strategies/api/saveSingleDiscoveryConfiguration';
import OfferingReferenceSelect from '../../configuration/discovery-strategies/components/OfferingReferenceSelect.vue';
import IcpReferenceSelect from '../../configuration/discovery-strategies/components/IcpReferenceSelect.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import { useDirtyDraft } from '../../../shared/forms/useDirtyDraft';
import ProfileSection from './ProfileSection.vue';
import { icpDescription } from '../lib/profileFormatting';

const emit = defineEmits<{
  editService: [service: { id: string; name: string; description: string }];
  createService: [];
  editIcp: [id?: string];
}>();
const session = useSession();
const client = useQueryClient();
const { strategies, singleStrategy } = useActiveDiscoveryStrategies();
const identity = computed(() =>
  [
    session.context.value?.account_id,
    session.context.value?.user_id,
    session.context.value?.csrf_token,
  ].join(':'),
);
const { draft, updateBaseline, accept, canLeave } = useDirtyDraft({ offeringId: '', icpId: '' });
const editing = ref(false);
const pending = ref(false);
const error = ref('');
const notice = ref('');
watch(
  singleStrategy,
  (selected) => {
    updateBaseline({
      offeringId: selected?.service_offering_id ?? '',
      icpId: selected?.ideal_client_profile_id ?? '',
    });
  },
  { immediate: true },
);
watch(
  identity,
  () => {
    accept({ offeringId: '', icpId: '' });
    editing.value = false;
    error.value = '';
    notice.value = '';
    pending.value = false;
  },
  { flush: 'sync' },
);
const references = useStrategyReferences(
  () => singleStrategy.value?.service_offering_id ?? draft.value.offeringId,
  () => singleStrategy.value?.ideal_client_profile_id ?? draft.value.icpId,
);
const offering = computed(
  () =>
    references.offeringItems.value.find(
      (item) => item.id === singleStrategy.value?.service_offering_id,
    ) ?? references.selectedOffering.data.value,
);
const icp = computed(
  () =>
    references.icpItems.value.find(
      (item) => item.id === singleStrategy.value?.ideal_client_profile_id,
    ) ?? references.selectedIcp.data.value,
);
const offeringOptions = computed(() => {
  const items = references.offeringItems.value;
  const selected = references.selectedOffering.data.value;
  return selected && !items.some((item) => item.id === selected.id) ? [...items, selected] : items;
});
const icpOptions = computed(() => {
  const items = references.icpItems.value;
  const selected = references.selectedIcp.data.value;
  return selected && !items.some((item) => item.id === selected.id) ? [...items, selected] : items;
});
const showSetup = computed(() => !singleStrategy.value || editing.value);
async function save() {
  if (pending.value || !draft.value.offeringId || !draft.value.icpId || strategies.isError.value)
    return;
  const requestedIdentity = identity.value;
  pending.value = true;
  error.value = '';
  const body = {
    service_offering_id: draft.value.offeringId,
    ideal_client_profile_id: draft.value.icpId,
  };
  try {
    await saveSingleDiscoveryConfiguration(body);
    if (requestedIdentity !== identity.value) return;
    accept({ offeringId: body.service_offering_id, icpId: body.ideal_client_profile_id });
    editing.value = false;
    await Promise.all([
      client.invalidateQueries({ queryKey: ['prospecting', requestedIdentity] }),
      client.invalidateQueries({
        queryKey: [
          'configuration',
          session.context.value?.account_id,
          session.context.value?.user_id,
          'strategies',
        ],
      }),
    ]);
    if (requestedIdentity === identity.value) notice.value = 'Discovery setup saved.';
  } catch {
    if (requestedIdentity === identity.value)
      error.value =
        'Discovery setup could not be saved. Your choices are retained. Retry Save discovery setup to confirm this pair.';
  } finally {
    if (requestedIdentity === identity.value) pending.value = false;
  }
}
async function cancel() {
  if (pending.value || !(await canLeave())) return;
  accept({
    offeringId: singleStrategy.value?.service_offering_id ?? '',
    icpId: singleStrategy.value?.ideal_client_profile_id ?? '',
  });
  editing.value = false;
}
defineExpose({ canClose: () => !pending.value && canLeave() });
</script>

<template>
  <ProfileSection title="Discovery setup">
    <LoadingState v-if="strategies.isPending.value" message="Loading discovery setup…" />
    <ErrorState v-else-if="strategies.isError.value" message="Discovery setup could not be loaded.">
      <Button
        label="Retry discovery setup"
        :disabled="strategies.isFetching.value"
        @click="strategies.refetch()"
      />
    </ErrorState>
    <template v-else>
      <form v-if="showSetup" class="setup-form" @submit.prevent="save">
        <p>
          Choose one service offering and ICP for your recommendations. Save this pair to start
          discovery.
        </p>
        <OfferingReferenceSelect
          v-model="draft.offeringId"
          :disabled="pending"
          :items="offeringOptions"
          :has-more="references.offerings.hasNextPage.value"
          :loading="references.offerings.isFetching.value"
          :unavailable="false"
          :error="
            references.offerings.isError.value ? 'Service offerings could not be loaded.' : ''
          "
          feedback=""
          hide-create-link
          @more="references.offerings.fetchNextPage()"
        />
        <Button
          v-if="references.offerings.isError.value"
          label="Retry service offerings"
          severity="secondary"
          @click="references.offerings.refetch()"
        />
        <Button
          v-else-if="
            !references.offerings.isPending.value &&
            !references.offeringItems.value.length &&
            !references.offerings.hasNextPage.value
          "
          label="Add a service"
          severity="secondary"
          @click="emit('createService')"
        />
        <IcpReferenceSelect
          v-model="draft.icpId"
          :disabled="pending"
          :items="icpOptions"
          :has-more="references.icps.hasNextPage.value"
          :loading="references.icps.isFetching.value"
          :unavailable="false"
          :error="references.icps.isError.value ? 'ICPs could not be loaded.' : ''"
          feedback=""
          hide-manage-link
          @more="references.icps.fetchNextPage()"
        />
        <Button
          v-if="references.icps.isError.value"
          label="Retry ICPs"
          severity="secondary"
          @click="references.icps.refetch()"
        />
        <Button
          v-else-if="
            !references.icps.isPending.value &&
            !references.icpItems.value.length &&
            !references.icps.hasNextPage.value
          "
          label="Add your ICP"
          severity="secondary"
          @click="emit('editIcp')"
        />
        <p v-if="error" role="alert">{{ error }}</p>
        <div class="setup-actions">
          <Button
            v-if="singleStrategy"
            label="Cancel"
            severity="secondary"
            :disabled="pending"
            @click="cancel"
          />
          <Button
            type="submit"
            label="Save discovery setup"
            :loading="pending"
            :disabled="
              pending ||
              !draft.offeringId ||
              !draft.icpId ||
              references.offerings.isError.value ||
              references.icps.isError.value
            "
          />
        </div>
      </form>
      <div v-else class="chosen-pair">
        <template v-if="offering">
          <h3>Service offering</h3>
          <button
            type="button"
            class="chosen-item"
            aria-label="Edit service offering"
            @click="emit('editService', offering)"
          >
            <strong>{{ offering.name }}</strong
            ><span>{{ offering.description }}</span>
          </button>
        </template>
        <ErrorState
          v-else-if="
            references.offerings.isError.value || references.selectedOffering.isError.value
          "
          message="Your service offering could not be loaded."
          ><Button
            label="Retry service offering"
            @click="
              references.offerings.refetch();
              references.selectedOffering.refetch();
            "
        /></ErrorState>
        <LoadingState v-else message="Loading service offering…" />
        <template v-if="icp">
          <h3>ICP definition</h3>
          <button
            type="button"
            class="chosen-item"
            aria-label="Edit ICP definition"
            @click="emit('editIcp', icp.id)"
          >
            <strong>{{ icp.name }}</strong
            ><span>{{ icpDescription(icp) }}</span>
          </button>
        </template>
        <ErrorState
          v-else-if="references.icps.isError.value || references.selectedIcp.isError.value"
          message="Your ICP could not be loaded."
          ><Button
            label="Retry ICP"
            @click="
              references.icps.refetch();
              references.selectedIcp.refetch();
            "
        /></ErrorState>
        <LoadingState v-else message="Loading ICP…" />
        <Button
          label="Change discovery setup"
          severity="secondary"
          :disabled="strategies.isFetching.value"
          @click="editing = true"
        />
      </div>
      <p v-if="notice" role="status">{{ notice }}</p>
    </template>
  </ProfileSection>
</template>

<style scoped>
.setup-form,
.chosen-pair,
.chosen-item {
  display: grid;
  gap: var(--space-3);
  min-width: 0;
}
.setup-form p,
.chosen-pair h3 {
  margin: 0;
}
.chosen-pair h3 {
  font-size: 1rem;
  font-weight: 600;
}
.chosen-item {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  padding: var(--space-4);
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.chosen-item:hover {
  background: var(--color-surface-muted);
}
.chosen-item span {
  color: var(--color-text-muted);
  white-space: pre-wrap;
}
.setup-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  justify-content: flex-end;
}
[role='alert'] {
  color: var(--color-danger-text);
}
</style>
