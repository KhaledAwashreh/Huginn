import { onMounted, onUnmounted, ref } from 'vue';

const CLOCK_INTERVAL_MS = 1_000;

export function useProspectClock() {
  const now = ref(Date.now());
  let interval: number | undefined;
  const refresh = () => {
    now.value = Date.now();
  };

  onMounted(() => {
    interval = window.setInterval(refresh, CLOCK_INTERVAL_MS);
    document.addEventListener('visibilitychange', refresh);
  });
  onUnmounted(() => {
    if (interval !== undefined) window.clearInterval(interval);
    document.removeEventListener('visibilitychange', refresh);
  });

  return now;
}
