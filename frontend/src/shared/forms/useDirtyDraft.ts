import { computed, getCurrentScope, onScopeDispose, ref, shallowRef, toRaw } from 'vue';

function cloneValue<T>(value: T): T {
  return structuredClone(toRaw(value));
}

function valuesEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (left === null || right === null || typeof left !== 'object' || typeof right !== 'object') {
    return false;
  }
  if (left instanceof Date || right instanceof Date) {
    return left instanceof Date && right instanceof Date && left.getTime() === right.getTime();
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => valuesEqual(item, right[index]))
    );
  }

  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const leftKeys = Object.keys(leftRecord);
  const rightKeys = Object.keys(rightRecord);
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key) => Object.hasOwn(rightRecord, key) && valuesEqual(leftRecord[key], rightRecord[key]),
    )
  );
}

export function useDirtyDraft<T>(initial: T, confirmLeave?: () => boolean | Promise<boolean>) {
  const baseline = shallowRef(cloneValue(initial));
  const draft = ref(cloneValue(initial));
  const dirty = computed(() => !valuesEqual(draft.value, baseline.value));

  function updateBaseline(next: T): void {
    const wasDirty = dirty.value;
    const nextBaseline = cloneValue(next);
    baseline.value = nextBaseline;
    if (!wasDirty) draft.value = cloneValue(nextBaseline);
  }

  function accept(next: T = draft.value): void {
    const accepted = cloneValue(next);
    baseline.value = accepted;
    draft.value = cloneValue(accepted);
  }

  function reset(): void {
    draft.value = cloneValue(baseline.value);
  }

  async function canLeave(): Promise<boolean> {
    if (!dirty.value) return true;
    if (confirmLeave) return confirmLeave();
    return typeof window === 'undefined' || window.confirm('Discard your unsaved changes?');
  }

  if (typeof window !== 'undefined' && getCurrentScope()) {
    const handleBeforeUnload = (event: BeforeUnloadEvent): void => {
      if (!dirty.value) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    onScopeDispose(() => window.removeEventListener('beforeunload', handleBeforeUnload));
  }

  return { draft, dirty, updateBaseline, accept, reset, canLeave };
}
