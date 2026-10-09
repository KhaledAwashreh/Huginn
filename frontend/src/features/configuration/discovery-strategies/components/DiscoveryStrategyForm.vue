<script setup lang="ts">
import { computed, ref, toRaw } from 'vue';
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import InputText from 'primevue/inputtext';
import Checkbox from 'primevue/checkbox';
import Button from 'primevue/button';
import { ApiError } from '../../../../api/apiError';
import type { components } from '../../../../api/generated/schema';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import { useDirtyDraft } from '../../../../shared/forms/useDirtyDraft';
import { useStrategyReferences } from '../composables/useStrategyReferences';
import { serializeDiscoveryStrategyPatch } from '../forms/serializeDiscoveryStrategyPatch';
import type { DiscoveryStrategyDraft } from '../forms/discoveryStrategyDraft';
import OfferingReferenceSelect from './OfferingReferenceSelect.vue';
import IcpReferenceSelect from './IcpReferenceSelect.vue';
const props = defineProps<{
  initial: DiscoveryStrategyDraft;
  creating: boolean;
  save: (
    draft: DiscoveryStrategyDraft,
    patch: components['schemas']['DiscoveryStrategyUpdateRequest'],
  ) => Promise<DiscoveryStrategyDraft>;
  refresh?: () => Promise<DiscoveryStrategyDraft | null>;
}>();
const emit = defineEmits<{ saved: [] }>();
const { draft, dirty, accept, reset, canLeave, updateBaseline } = useDirtyDraft(props.initial);
const baseline = ref<DiscoveryStrategyDraft>(structuredClone(toRaw(props.initial)));
const refs = useStrategyReferences(
  () => draft.value.service_offering_id,
  () => draft.value.ideal_client_profile_id,
);
const pending = ref(false);
const error = ref<ApiError | null>(null);
const message = ref('');
const uncertain = ref(false);
const refreshed = ref(false);
const offeringOptions = computed(() => {
  const options = refs.offeringItems.value.slice();
  const selected = refs.selectedOffering.data.value;
  if (selected && !options.some((item) => item.id === selected.id)) options.push(selected);
  return options;
});
const icpOptions = computed(() => {
  const options = refs.icpItems.value.slice();
  const selected = refs.selectedIcp.data.value;
  if (selected && !options.some((item) => item.id === selected.id)) options.push(selected);
  return options;
});
const offeringLoaded = computed(() =>
  refs.offeringItems.value.some((item) => item.id === draft.value.service_offering_id),
);
const icpLoaded = computed(() =>
  refs.icpItems.value.some((item) => item.id === draft.value.ideal_client_profile_id),
);
const offeringUnavailable = computed(
  () =>
    !offeringLoaded.value &&
    refs.selectedOffering.error.value instanceof ApiError &&
    refs.selectedOffering.error.value.status === 404,
);
const icpUnavailable = computed(
  () =>
    !icpLoaded.value &&
    refs.selectedIcp.error.value instanceof ApiError &&
    refs.selectedIcp.error.value.status === 404,
);
const referencePending = computed(
  () =>
    (!offeringLoaded.value && refs.selectedOffering.isFetching.value) ||
    (!icpLoaded.value && refs.selectedIcp.isFetching.value),
);
const referenceFailed = computed(
  () =>
    (!offeringLoaded.value && refs.selectedOffering.isError.value) ||
    (!icpLoaded.value && refs.selectedIcp.isError.value),
);
const hasChanges = computed(() => props.creating || dirty.value);
function feedback(field: string): string {
  return (
    error.value?.fields
      .filter((item) => item.path[0] === field)
      .map((item) => item.message)
      .join(' ') ?? ''
  );
}
function referenceError(error: unknown): string {
  return error && !(error instanceof ApiError && error.status === 404)
    ? 'References could not be loaded. Reload before saving.'
    : '';
}
async function submit(): Promise<void> {
  if (
    pending.value ||
    !hasChanges.value ||
    referencePending.value ||
    referenceFailed.value ||
    (uncertain.value && !refreshed.value)
  )
    return;
  message.value = '';
  error.value = null;
  if (
    !draft.value.name.trim() ||
    !draft.value.service_offering_id ||
    !draft.value.ideal_client_profile_id
  ) {
    message.value = 'Enter a name and choose one offering and one ICP.';
    return;
  }
  pending.value = true;
  try {
    const patch = serializeDiscoveryStrategyPatch(baseline.value, draft.value);
    if (!props.creating && !Object.keys(patch).length) {
      message.value = 'Your draft matches the saved data.';
      return;
    }
    const saved = await props.save(draft.value, patch);
    baseline.value = structuredClone(toRaw(saved));
    accept(saved);
    uncertain.value = false;
    refreshed.value = false;
    message.value = 'Strategy saved.';
    pending.value = false;
    emit('saved');
  } catch (failure) {
    if (failure instanceof ApiError && failure.status < 500) {
      error.value = failure;
      message.value = failure.message;
    } else {
      uncertain.value = true;
      refreshed.value = false;
      message.value =
        'The save response was lost. Your draft is preserved. Refresh saved data before deciding whether to save again.';
    }
  } finally {
    pending.value = false;
  }
}
async function refreshSaved(): Promise<void> {
  if (pending.value || !props.refresh) return;
  pending.value = true;
  try {
    const saved = await props.refresh();
    if (saved) {
      baseline.value = structuredClone(toRaw(saved));
      updateBaseline(saved);
    }
    refreshed.value = true;
    message.value = saved
      ? 'Saved data refreshed. Your draft is preserved. Cancel restores the saved values, or review your changes and save deliberately.'
      : 'Saved strategies refreshed. Your draft is preserved. Check the strategy list for a completed creation before deliberately creating another.';
  } catch (failure) {
    message.value =
      failure instanceof ApiError
        ? failure.message
        : 'Saved data could not be refreshed. Your draft is preserved.';
  } finally {
    pending.value = false;
  }
}
function cancel(): void {
  if (pending.value) return;
  accept(baseline.value);
  reset();
  error.value = null;
  message.value = '';
  uncertain.value = false;
  refreshed.value = false;
}
onBeforeRouteLeave(() => (pending.value ? false : canLeave()));
onBeforeRouteUpdate(() => (pending.value ? false : canLeave()));
</script>
<template>
  <form class="configuration-form" @submit.prevent="submit">
    <div class="field">
      <label for="strategy-name">Name</label
      ><InputText
        id="strategy-name"
        v-model="draft.name"
        :disabled="pending"
        required
        :aria-invalid="Boolean(feedback('name'))"
        aria-describedby="strategy-name-feedback"
      /><FieldFeedback id="strategy-name-feedback" :message="feedback('name')" />
    </div>
    <OfferingReferenceSelect
      v-model="draft.service_offering_id"
      :disabled="pending"
      :items="offeringOptions"
      :has-more="refs.offerings.hasNextPage.value"
      :loading="refs.offerings.isFetching.value"
      :unavailable="offeringUnavailable"
      :error="
        referenceError(
          refs.offerings.error.value || (!offeringLoaded && refs.selectedOffering.error.value),
        )
      "
      :feedback="feedback('service_offering_id')"
      @more="refs.offerings.fetchNextPage()"
    />
    <IcpReferenceSelect
      v-model="draft.ideal_client_profile_id"
      :disabled="pending"
      :items="icpOptions"
      :has-more="refs.icps.hasNextPage.value"
      :loading="refs.icps.isFetching.value"
      :unavailable="icpUnavailable"
      :error="referenceError(refs.icps.error.value || (!icpLoaded && refs.selectedIcp.error.value))"
      :feedback="feedback('ideal_client_profile_id')"
      @more="refs.icps.fetchNextPage()"
    />
    <div class="checkbox-field">
      <Checkbox
        v-model="draft.is_active"
        :disabled="pending"
        input-id="strategy-active"
        binary
      /><label for="strategy-active">Active strategy</label>
    </div>
    <p>Active strategies participate in future matching runs. Saving does not run matching.</p>
    <FieldFeedback :message="error || uncertain ? message : ''" />
    <p v-if="message && !error && !uncertain" role="status">{{ message }}</p>
    <div class="form-actions">
      <Button
        type="submit"
        :label="creating ? 'Create strategy' : 'Save changes'"
        :loading="pending"
        :disabled="
          pending || !hasChanges || referencePending || referenceFailed || (uncertain && !refreshed)
        "
      /><Button
        type="button"
        label="Cancel"
        severity="secondary"
        :disabled="pending"
        @click="cancel"
      /><Button
        v-if="uncertain && refresh"
        type="button"
        label="Refresh saved data"
        severity="secondary"
        :disabled="pending"
        @click="refreshSaved"
      />
    </div>
    <p v-if="creating && uncertain">
      The create result is uncertain. Return to the strategy list and check whether it was created
      before creating another.
    </p>
  </form>
</template>
