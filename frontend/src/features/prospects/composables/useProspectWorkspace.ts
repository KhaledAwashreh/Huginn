import { computed, reactive, ref, shallowRef, watch, type ComputedRef } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { getProspect } from '../api/getProspect';
import { listProspects } from '../api/listProspects';
import { createProspectCommandDraft, hasProspectDraft } from '../models/prospectCommandDraft';
import type { ProspectCommandDraft } from '../models/prospectCommandDraft';
import type { ProspectStage, ProspectView } from '../models/prospect';

export const PROSPECT_PAGE_SIZE = 25;
const draftRegistry = new Map<string, Map<string, ProspectCommandDraft>>();

function draftsForIdentity(identity: string): Map<string, ProspectCommandDraft> {
  let drafts = draftRegistry.get(identity);
  if (!drafts) {
    drafts = reactive(new Map<string, ProspectCommandDraft>());
    draftRegistry.set(identity, drafts);
  }
  return drafts;
}

export interface ProspectRecovery {
  prospectId: string;
  snapshot: ProspectView;
  draft: ProspectCommandDraft;
}

export function useProspectWorkspace(selectedId: ComputedRef<string | null>) {
  const session = useSession();
  const queryClient = useQueryClient();
  const identity = computed(() =>
    [
      session.context.value?.account_id,
      session.context.value?.user_id,
      session.context.value?.csrf_token,
    ].join(':'),
  );
  const search = ref('');
  const stage = ref<ProspectStage | 'all'>('all');
  const offset = ref(0);
  const commandDrafts = shallowRef(draftsForIdentity(identity.value));
  const listKey = computed(
    () =>
      [
        'prospects',
        identity.value,
        'list',
        stage.value,
        search.value.trim(),
        offset.value,
      ] as const,
  );
  const detailKey = computed(
    () => ['prospects', identity.value, 'detail', selectedId.value] as const,
  );

  const prospects = useQuery({
    queryKey: listKey,
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: ({ signal }) =>
      listProspects(
        {
          stage: stage.value,
          search: search.value,
          offset: offset.value,
          limit: PROSPECT_PAGE_SIZE,
        },
        signal,
      ),
  });
  const detail = useQuery({
    queryKey: detailKey,
    enabled: computed(() => Boolean(session.context.value && selectedId.value)),
    queryFn: ({ signal }) => {
      const prospectId = selectedId.value;
      if (!prospectId) throw new Error('Select a prospect to view its details.');
      return getProspect(prospectId, signal);
    },
  });

  watch([search, stage], () => {
    offset.value = 0;
  });
  watch(
    identity,
    (next, previous) => {
      draftRegistry.delete(previous);
      commandDrafts.value = draftsForIdentity(next);
      search.value = '';
      stage.value = 'all';
      offset.value = 0;
    },
    { flush: 'sync' },
  );

  function commandDraftFor(prospectId: string, snapshot?: ProspectView): ProspectCommandDraft {
    let draft = commandDrafts.value.get(prospectId);
    if (!draft) {
      draft = reactive(createProspectCommandDraft(prospectId));
      commandDrafts.value.set(prospectId, draft);
    }
    if (snapshot && (!draft.snapshot || (!hasProspectDraft(draft) && draft.status === 'idle'))) {
      draft.snapshot = snapshot;
      if (draft.expectedVersion === null) draft.notes = snapshot.notes;
    }
    return draft;
  }

  const recoveries = computed<ProspectRecovery[]>(() =>
    [...commandDrafts.value.values()].flatMap((draft) =>
      hasProspectDraft(draft) && draft.snapshot
        ? [{ prospectId: draft.prospectId, snapshot: draft.snapshot, draft }]
        : [],
    ),
  );

  function discardDraft(prospectId: string): void {
    const draft = commandDrafts.value.get(prospectId);
    if (!draft || draft.status === 'pending' || draft.status === 'uncertain') return;
    commandDrafts.value.delete(prospectId);
  }

  function setOffset(value: number): void {
    offset.value = Math.max(0, value);
  }

  async function refresh(prospectId?: string): Promise<void> {
    const requestedIdentity = identity.value;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['prospects', requestedIdentity, 'list'] }),
      ...(prospectId
        ? [
            queryClient.invalidateQueries({
              queryKey: ['prospects', requestedIdentity, 'detail', prospectId],
            }),
          ]
        : []),
    ]);
  }

  return {
    identity,
    search,
    stage,
    offset,
    prospects,
    detail,
    listKey,
    detailKey,
    commandDrafts,
    recoveries,
    commandDraftFor,
    discardDraft,
    setOffset,
    refresh,
  };
}
