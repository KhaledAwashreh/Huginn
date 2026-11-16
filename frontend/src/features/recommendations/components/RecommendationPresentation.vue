<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import type { RecommendationView } from '../models/prospecting';
import { useRecommendationPresentation } from '../composables/useRecommendationPresentation';

const props = withDefaults(
  defineProps<{
    recommendation: RecommendationView;
    identity: string;
    historical?: boolean;
  }>(),
  { historical: false },
);
const emit = defineEmits<{ confirmed: [] }>();
const { state, prepare, confirm } = useRecommendationPresentation(props);
const element = ref<HTMLElement | null>(null);
const visible = ref(false);
const foreground = ref(document.visibilityState === 'visible');
const readable = computed(
  () =>
    !state.value ||
    (!['idle', 'preparing'].includes(state.value.status) &&
      !(state.value.status === 'uncertain' && !state.value.preparation)),
);
const shownRecommendation = computed(() =>
  state.value && ['preparing', 'rendered', 'confirming', 'uncertain'].includes(state.value.status)
    ? state.value.snapshot
    : props.recommendation,
);
const unresolved = computed(() =>
  Boolean(state.value && ['preparing', 'confirming', 'uncertain'].includes(state.value.status)),
);
let observer: IntersectionObserver | null = null;
let observedNode: Element | null = null;
let active = true;

function isVisible(): boolean {
  const node = element.value;
  if (!active || !node?.isConnected || !visible.value || !foreground.value) return false;
  const assessment = node.querySelector('[data-assessment-revision-id]');
  const target = state.value?.preparation ? assessment : node;
  if (
    !target ||
    (assessment &&
      assessment.getAttribute('data-assessment-revision-id') !==
        state.value?.snapshot.assessment?.id)
  )
    return false;
  const box = target.getBoundingClientRect();
  return (
    box.width > 0 &&
    box.height > 0 &&
    box.bottom > 0 &&
    box.top < window.innerHeight &&
    box.right > 0 &&
    box.left < window.innerWidth
  );
}
function observe(node: Element): void {
  if (node === observedNode || !observer) return;
  observer.disconnect();
  observedNode = node;
  visible.value = false;
  observer.observe(node);
}
watch(
  () => state.value?.status,
  async (status) => {
    if (status !== 'rendered') return;
    await nextTick();
    const assessment = element.value?.querySelector('[data-assessment-revision-id]');
    if (active && assessment) observe(assessment);
  },
);
async function confirmRendered(): Promise<void> {
  const target = state.value;
  await nextTick();
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  if (state.value === target && isVisible() && (await confirm())) emit('confirmed');
}
watch(
  () => [visible.value, foreground.value, state.value?.status] as const,
  async () => {
    if (!isVisible()) return;
    if (state.value?.status === 'idle') await prepare();
    else if (state.value?.status === 'rendered') await confirmRendered();
  },
);
async function retry(): Promise<void> {
  if (!isVisible()) return;
  if (state.value?.preparation) await confirmRendered();
  else await prepare();
}
function visibilityChanged(): void {
  foreground.value = document.visibilityState === 'visible';
}
function beforeUnload(event: BeforeUnloadEvent): void {
  if (unresolved.value) {
    event.preventDefault();
    event.returnValue = '';
  }
}
onBeforeRouteLeave(
  () => !unresolved.value || window.confirm('Presentation is still unconfirmed. Leave this page?'),
);
onMounted(() => {
  if (typeof IntersectionObserver !== 'undefined' && element.value) {
    observer = new IntersectionObserver((entries) => {
      visible.value = entries.some((entry) => entry.isIntersecting);
    });
    const assessment =
      state.value?.preparation && element.value.querySelector('[data-assessment-revision-id]');
    observe(assessment || element.value);
  }
  document.addEventListener('visibilitychange', visibilityChanged);
  window.addEventListener('beforeunload', beforeUnload);
});
onUnmounted(() => {
  active = false;
  observer?.disconnect();
  document.removeEventListener('visibilitychange', visibilityChanged);
  window.removeEventListener('beforeunload', beforeUnload);
});
</script>

<template>
  <div ref="element">
    <template v-if="readable">
      <slot :recommendation="shownRecommendation" />
    </template>
    <p v-else role="status">
      {{
        state?.status === 'uncertain'
          ? 'Presentation is unconfirmed.'
          : `Preparing ${recommendation.company.name}…`
      }}
    </p>
    <p v-if="state?.error" role="status">{{ state.error }}</p>
    <button v-if="state?.status === 'uncertain'" type="button" @click="retry">
      Retry presentation
    </button>
  </div>
</template>
