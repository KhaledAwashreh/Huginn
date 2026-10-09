<script setup lang="ts">
import { computed, ref } from 'vue';
import { useInfiniteQuery, useQuery } from '@tanstack/vue-query';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Button from 'primevue/button';
import { ApiError } from '../../../../api/apiError';
import { useSession } from '../../../session/composables/useSession';
import { getCompanyOption } from '../api/getCompanyOption';
import { listCompanyOptions } from '../api/listCompanyOptions';

const props = defineProps<{
  id: string;
  inputKey: string;
  errorId?: string | undefined;
  disabled?: boolean;
  invalid?: boolean;
}>();
const emit = defineEmits<{ 'update:id': [id: string] }>();
const session = useSession();
const search = ref('');
const scope = computed(() => [
  'configuration',
  session.context.value?.account_id,
  session.context.value?.user_id,
  'company-options',
]);
const enabled = computed(() => session.context.value !== null);
const pages = useInfiniteQuery({
  queryKey: computed(() => [...scope.value, search.value.trim()]),
  enabled,
  initialPageParam: 0,
  queryFn: ({ pageParam, signal }) =>
    listCompanyOptions(search.value.trim(), pageParam, 50, signal),
  getNextPageParam: (page) => (page.has_more ? page.offset + page.limit : undefined),
  retry: false,
});
const items = computed(() => pages.data.value?.pages.flatMap((page) => page.items) ?? []);
const selectedQuery = useQuery({
  queryKey: computed(() => [...scope.value, 'selected', props.id]),
  enabled: computed(
    () => enabled.value && Boolean(props.id) && !items.value.some((item) => item.id === props.id),
  ),
  queryFn: ({ signal }) => getCompanyOption(props.id, signal),
  retry: false,
});
const selectedCompany = computed(
  () => items.value.find((item) => item.id === props.id) ?? selectedQuery.data.value,
);
const selectedUnavailable = computed(
  () =>
    Boolean(props.id) &&
    !selectedCompany.value &&
    selectedQuery.error.value instanceof ApiError &&
    selectedQuery.error.value.status === 404,
);
const selectedLoadFailed = computed(
  () =>
    Boolean(props.id) &&
    !selectedCompany.value &&
    Boolean(selectedQuery.error.value) &&
    !selectedUnavailable.value,
);
const selectedFallback = computed(() =>
  props.id && !selectedCompany.value
    ? {
        id: props.id,
        name: selectedUnavailable.value
          ? 'Unavailable saved company'
          : selectedLoadFailed.value
            ? 'Saved company label unavailable'
            : 'Loading saved company…',
        domain: null,
        disabled: true,
      }
    : null,
);
const options = computed(() =>
  selectedCompany.value && !items.value.some((item) => item.id === selectedCompany.value?.id)
    ? [selectedCompany.value, ...items.value]
    : selectedFallback.value
      ? [selectedFallback.value, ...items.value]
      : items.value,
);
function companyLabel(company: { name: string; domain: string | null }): string {
  return company.domain ? `${company.name} · ${company.domain}` : company.name;
}
</script>

<template>
  <div class="company-picker">
    <label :for="`company-search-${props.inputKey}`"
      >Search public companies by name or domain</label
    >
    <InputText
      :id="`company-search-${props.inputKey}`"
      v-model="search"
      :disabled="disabled"
      autocomplete="off"
      placeholder="Search companies"
    />
    <p v-if="pages.isPending.value" role="status">Loading companies…</p>
    <p v-else-if="pages.isError.value" role="alert">Company search could not be loaded.</p>
    <p v-else-if="items.length === 0" role="status">No collected companies match this search.</p>
    <template v-if="items.length > 0 || selectedFallback || selectedCompany">
      <label
        :id="`company-choice-label-${props.inputKey}`"
        :for="`company-choice-${props.inputKey}`"
        >Company</label
      >
      <Select
        :input-id="`company-choice-${props.inputKey}`"
        :aria-labelledby="`company-choice-label-${props.inputKey}`"
        :model-value="props.id"
        :options="options"
        option-label="name"
        option-value="id"
        option-disabled="disabled"
        :disabled="disabled"
        :invalid="invalid"
        :aria-describedby="errorId"
        :filter="false"
        :placeholder="'Choose a collected company'"
        @update:model-value="emit('update:id', $event)"
      >
        <template #option="slotProps">
          {{ companyLabel(slotProps.option) }}
        </template>
      </Select>
      <Button
        v-if="pages.hasNextPage.value"
        type="button"
        severity="secondary"
        label="Load more companies"
        :disabled="disabled || pages.isFetchingNextPage.value"
        :loading="pages.isFetchingNextPage.value"
        @click="pages.fetchNextPage()"
      />
    </template>
    <p v-if="selectedQuery.isFetching.value && !selectedCompany && props.id" role="status">
      Loading saved company…
    </p>
    <p v-else-if="selectedUnavailable" class="notice" role="status">
      Saved company {{ props.id }} is unavailable in the public directory. It remains selected until
      you remove this exclusion.
    </p>
    <p v-else-if="selectedLoadFailed" role="alert">
      The saved company label could not be loaded. The exclusion remains selected.
    </p>
    <p v-else-if="selectedCompany" class="selected-label">
      Selected: {{ companyLabel(selectedCompany) }}
    </p>
  </div>
</template>

<style scoped>
.company-picker {
  display: grid;
  gap: var(--space-2);
}
.notice,
.selected-label {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}
</style>
