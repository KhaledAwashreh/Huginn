import { effectScope } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import { useDirtyDraft } from '@/shared/forms/useDirtyDraft';

interface ProfileDraft {
  name: string;
  tags: string[];
}

const makeDraft = (): ProfileDraft => ({ name: 'Ada', tags: ['founder'] });

describe('useDirtyDraft', () => {
  it('clones initial values and tracks nested edits to the draft', () => {
    const initial = makeDraft();
    const { draft, dirty } = useDirtyDraft(initial);

    expect(draft.value).toEqual(initial);
    expect(draft.value).not.toBe(initial);
    expect(draft.value.tags).not.toBe(initial.tags);
    expect(dirty.value).toBe(false);

    draft.value.tags.push('operator');
    expect(dirty.value).toBe(true);
    expect(initial.tags).toEqual(['founder']);
  });

  it('preserves a dirty draft when background data refreshes', () => {
    const { draft, dirty, updateBaseline } = useDirtyDraft(makeDraft());
    draft.value = { ...draft.value, name: 'Ada Lovelace' };

    updateBaseline({ name: 'Ada Byron', tags: ['founder', 'operator'] });

    expect(draft.value).toEqual({ name: 'Ada Lovelace', tags: ['founder'] });
    expect(dirty.value).toBe(true);
  });

  it('refreshes a clean draft and accepts saved values as the new baseline', () => {
    const { draft, dirty, updateBaseline, accept, reset } = useDirtyDraft(makeDraft());
    updateBaseline({ name: 'Ada Byron', tags: ['operator'] });
    expect(draft.value).toEqual({ name: 'Ada Byron', tags: ['operator'] });

    draft.value = { ...draft.value, name: 'Ada Lovelace' };
    accept({ name: 'Ada Lovelace', tags: ['operator'] });
    expect(dirty.value).toBe(false);

    draft.value = { ...draft.value, name: 'Unsaved change' };
    reset();
    expect(draft.value).toEqual({ name: 'Ada Lovelace', tags: ['operator'] });
    expect(dirty.value).toBe(false);
  });

  it('asks the caller before leaving a dirty draft', async () => {
    const confirmLeave = vi.fn().mockResolvedValue(false);
    const { draft, canLeave } = useDirtyDraft(makeDraft(), confirmLeave);
    draft.value = { ...draft.value, name: 'Unsaved change' };

    await expect(canLeave()).resolves.toBe(false);
    expect(confirmLeave).toHaveBeenCalledOnce();
  });

  it('allows clean drafts without prompting and uses the browser prompt by default', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { draft, canLeave } = useDirtyDraft(makeDraft());

    await expect(canLeave()).resolves.toBe(true);
    expect(confirm).not.toHaveBeenCalled();

    draft.value = { ...draft.value, name: 'Unsaved change' };
    await expect(canLeave()).resolves.toBe(false);
    expect(confirm).toHaveBeenCalledOnce();
  });

  it('guards beforeunload while dirty and removes the listener when its scope ends', () => {
    const scope = effectScope();
    const state = scope.run(() => useDirtyDraft(makeDraft()));
    if (!state) throw new Error('Expected a scoped draft');
    state.draft.value = { ...state.draft.value, name: 'Unsaved change' };

    const blocked = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(blocked);
    expect(blocked.defaultPrevented).toBe(true);

    scope.stop();
    const allowed = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(allowed);
    expect(allowed.defaultPrevented).toBe(false);
  });
});
