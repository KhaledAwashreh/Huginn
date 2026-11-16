<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, useId } from 'vue';
import { matchedRouteKey, onBeforeRouteLeave } from 'vue-router';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import Textarea from 'primevue/textarea';
import { ApiError } from '../../../api/apiError';
import { awaitingBackendAttrs } from '../../../shared/availability/awaitingBackend';
import { openSettingsKey } from '../../../shared/navigation/settingsSections';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import { useAccount } from '../../configuration/account/composables/useAccount';
import { useIdealClientProfile } from '../../configuration/ideal-client-profiles/composables/useIdealClientProfile';
import { useServiceOffering } from '../../configuration/offerings/composables/useServiceOffering';
import { serializeServiceOfferingPatch } from '../../configuration/offerings/forms/serializeServiceOfferingPatch';
import { useProfessionalProfile } from '../../configuration/professional-profile/composables/useProfessionalProfile';
import SkillRows from '../../configuration/professional-profile/components/SkillRows.vue';
import type { SkillDraft } from '../../configuration/professional-profile/forms/professionalProfileDraft';
import { useMatchReactions } from '../../matches/composables/useMatchReactions';
import { canonicalFeedbackReason } from '../../recommendations/models/canonicalFeedbackReason';
import BusinessCard from '../components/BusinessCard.vue';
import BusinessProfileForm from '../components/BusinessProfileForm.vue';
import ProfileSection from '../components/ProfileSection.vue';
import { useBusinessProfile } from '../composables/useBusinessProfile';
import { icpDescription } from '../lib/profileFormatting';
import {
  describeServiceMutationFailure,
  type ServiceMutationFailure,
} from '../lib/serviceMutationFailure';

type Editing = { kind: 'about' } | { kind: 'skills' } | { kind: 'service'; id: string | null };

const openSettings = inject(openSettingsKey, null);
const availabilityScope = useId();
const { account } = useAccount();
const { profile, save } = useProfessionalProfile();
const { business } = useBusinessProfile();
const serviceOffset = ref(0);
const servicePageSize = 100;
const offerings = useServiceOffering(undefined, serviceOffset, servicePageSize);
const icps = useIdealClientProfile();
const { allReactions } = useMatchReactions();

const data = computed(() => profile.data.value);
const businessData = computed(() => business.data.value);
const ownerName = computed(() =>
  `${account.data.value?.first_name ?? ''} ${account.data.value?.last_name ?? ''}`.trim(),
);
const initials = (name: string) =>
  name
    .split(/\s+/)
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
const servicesEmpty = computed(
  () =>
    serviceOffset.value === 0 &&
    !offerings.list.isError.value &&
    offerings.list.data.value?.items.length === 0,
);
const icpsEmpty = computed(
  () => !icps.list.isError.value && icps.list.data.value?.items.length === 0,
);

const editing = ref<Editing | null>(null);
const businessEditorVisible = ref(false);
const businessForm = ref<InstanceType<typeof BusinessProfileForm> | null>(null);
const fields = ref<Record<string, string>>({});
const initialFields = ref<Record<string, string>>({});
const skills = ref<SkillDraft[]>([]);
const initialSkills = ref('[]');
const opened = ref('');
const pending = ref(false);
const error = ref('');
const outcomeUncertain = ref(false);

const snapshot = () => JSON.stringify([fields.value, skills.value]);
const dialogTitle = computed(() => {
  const current = editing.value;
  if (!current) return '';
  if (current.kind === 'about') return 'Professional summary';
  if (current.kind === 'skills') return 'Skills';
  return current.id ? 'Edit service' : 'Add a service';
});
const canDelete = computed(() => {
  const current = editing.value;
  return current?.kind === 'service' && current.id !== null;
});

function open(next: Editing, values: Record<string, string>): void {
  editing.value = next;
  fields.value = values;
  initialFields.value = { ...values };
  skills.value =
    next.kind === 'skills' ? (data.value?.skills ?? []).map(({ name }) => ({ name })) : [];
  initialSkills.value = JSON.stringify(skills.value);
  opened.value = snapshot();
  error.value = '';
  outcomeUncertain.value = false;
}
function editBusiness(): void {
  businessEditorVisible.value = true;
}
function editAbout(): void {
  open({ kind: 'about' }, { summary: data.value?.professional_summary ?? '' });
}
function editSkills(): void {
  open({ kind: 'skills' }, {});
}
function editService(service?: { id: string; name: string; description: string }): void {
  open(
    { kind: 'service', id: service?.id ?? null },
    { name: service?.name ?? '', description: service?.description ?? '' },
  );
}

const dirty = computed(() => editing.value !== null && snapshot() !== opened.value);

function canClose(): boolean {
  return !pending.value && (!dirty.value || window.confirm('Discard your unsaved changes?'));
}

async function canLeaveProfile(): Promise<boolean> {
  if (!canClose()) return false;
  return businessForm.value?.canClose ? await businessForm.value.canClose() : true;
}

if (inject(matchedRouteKey, null)) onBeforeRouteLeave(canLeaveProfile);

function protectDraft(event: BeforeUnloadEvent): void {
  if (!dirty.value && !pending.value) return;
  event.preventDefault();
  event.returnValue = '';
}

onMounted(() => window.addEventListener('beforeunload', protectDraft));
onUnmounted(() => window.removeEventListener('beforeunload', protectDraft));

function close(): void {
  if (!canClose()) return;
  editing.value = null;
}
function generalFailure(failure: unknown): ServiceMutationFailure {
  return {
    message:
      failure instanceof ApiError || failure instanceof Error
        ? failure.message
        : 'This could not be saved. Try again.',
    outcomeUncertain: false,
  };
}

function profileFailure(failure: unknown): ServiceMutationFailure {
  if (failure instanceof ApiError && failure.status < 500) return generalFailure(failure);
  return {
    message: 'The save outcome is unknown. Refresh the saved profile before trying again.',
    outcomeUncertain: true,
  };
}

async function persist(
  action: () => Promise<unknown>,
  describeFailure: (failure: unknown) => ServiceMutationFailure = generalFailure,
): Promise<void> {
  pending.value = true;
  error.value = '';
  try {
    await action();
    editing.value = null;
  } catch (failure) {
    const described = describeFailure(failure);
    error.value = described.message;
    outcomeUncertain.value = described.outcomeUncertain;
  } finally {
    pending.value = false;
  }
}

async function refreshServices(): Promise<void> {
  if (pending.value) return;
  pending.value = true;
  const result = await offerings.list.refetch();
  pending.value = false;
  if (result.isError || !result.data) {
    error.value = 'Your services could not be refreshed. Try Refresh services again.';
    return;
  }
  if (editing.value?.kind === 'service' && editing.value.id === null) {
    // A create has no returned ID after a lost response. A refreshed page cannot
    // establish its identity, even if it contains a service with matching text.
    error.value =
      'Your new service is still unconfirmed. Your draft is retained. Cancel to discard the draft and review your saved services before adding it again.';
    return;
  }
  outcomeUncertain.value = false;
  error.value = '';
  editing.value = null;
}

async function refreshProfile(): Promise<void> {
  if (pending.value) return;
  pending.value = true;
  try {
    const result = await profile.refetch();
    if (result.isError || !result.data) {
      error.value = 'The saved profile could not be refreshed. Your draft is still here.';
      return;
    }
    outcomeUncertain.value = false;
    error.value = 'Saved profile refreshed. Review your draft before saving again.';
  } finally {
    pending.value = false;
  }
}

async function submit(): Promise<void> {
  const current = editing.value;
  const profileData = data.value;
  if (!current || !profileData || pending.value || outcomeUncertain.value) return;
  const value = fields.value;
  const describeFailure =
    current.kind === 'service' ? describeServiceMutationFailure : profileFailure;
  if (current.kind === 'skills' && skills.value.some(({ name }) => !name.trim())) {
    error.value = 'Enter a name for each skill or remove the empty row.';
    return;
  }
  if (current.kind === 'about' || current.kind === 'skills') {
    const baseline =
      current.kind === 'about' ? initialFields.value.summary?.trim() || null : initialSkills.value;
    const draft =
      current.kind === 'about'
        ? value.summary?.trim() || null
        : JSON.stringify(skills.value.map(({ name }) => ({ name: name.trim() })));
    const saved =
      current.kind === 'about'
        ? profileData.professional_summary
        : JSON.stringify(profileData.skills);
    if (draft === baseline || draft === saved) {
      editing.value = null;
      return;
    }
    if (
      saved !== baseline &&
      !window.confirm(
        `Your saved ${current.kind === 'about' ? 'summary' : 'skills'} changed while you were editing. Replace the saved value with your draft?`,
      )
    )
      return;
  }
  await persist(async () => {
    if (current.kind === 'about') {
      const summary = (value.summary ?? '').trim() || null;
      if (summary !== profileData.professional_summary)
        await save.mutateAsync({ professional_summary: summary });
    } else if (current.kind === 'skills') {
      const nextSkills = skills.value.map(({ name }) => ({ name: name.trim() }));
      if (JSON.stringify(nextSkills) !== JSON.stringify(profileData.skills))
        await save.mutateAsync({ skills: nextSkills });
    } else {
      const body = {
        name: (value.name ?? '').trim(),
        description: (value.description ?? '').trim(),
      };
      if (current.id) {
        const patch = serializeServiceOfferingPatch(
          {
            name: initialFields.value.name ?? '',
            description: initialFields.value.description ?? '',
          },
          body,
        );
        if (patch) await offerings.update.mutateAsync({ id: current.id, body: patch });
      } else await offerings.create.mutateAsync(body);
    }
  }, describeFailure);
}

async function removeItem(): Promise<void> {
  const current = editing.value;
  const profileData = data.value;
  if (!current || !profileData || outcomeUncertain.value) return;
  if (!window.confirm('Remove this from your profile?')) return;
  const describeFailure =
    current.kind === 'service' ? describeServiceMutationFailure : generalFailure;
  await persist(async () => {
    if (current.kind === 'service' && current.id) {
      await offerings.remove.mutateAsync(current.id);
    }
  }, describeFailure);
}
</script>

<template>
  <div class="profile-page">
    <PageHeader title="Profile" />
    <LoadingState v-if="profile.isPending.value && !data" message="Loading your profile…" />
    <ErrorState
      v-else-if="profile.isError.value && !data"
      message="Your profile could not be loaded."
    >
      <Button
        label="Retry profile"
        :disabled="profile.isFetching.value"
        @click="profile.refetch()"
      />
    </ErrorState>
    <template v-else-if="data">
      <BusinessCard v-if="businessData" :business="businessData" @edit="editBusiness" />
      <ErrorState
        v-else-if="business.isError.value"
        message="Business details could not be loaded."
      >
        <Button
          label="Retry business details"
          :disabled="business.isFetching.value"
          @click="business.refetch()"
        />
      </ErrorState>
      <LoadingState v-else message="Loading Business details…" />

      <ProfileSection v-if="businessData" title="About your business">
        <button
          type="button"
          class="item"
          aria-label="Edit business description"
          @click="editBusiness"
        >
          <span v-if="businessData.description" class="body-text">{{
            businessData.description
          }}</span>
          <span v-else class="placeholder">Describe what your business does.</span>
        </button>
      </ProfileSection>

      <ProfileSection title="Professional summary">
        <button
          type="button"
          class="item"
          aria-label="Edit professional summary"
          @click="editAbout"
        >
          <span v-if="data.professional_summary" class="body-text">{{
            data.professional_summary
          }}</span>
          <span v-else class="placeholder">Add a personal professional summary.</span>
        </button>
      </ProfileSection>
      <BusinessProfileForm
        v-if="businessData && businessEditorVisible"
        ref="businessForm"
        v-model:visible="businessEditorVisible"
        :profile="businessData"
      />

      <ProfileSection
        title="ICP definition"
        :add-label="icpsEmpty ? 'Add your ICP' : undefined"
        @add="openSettings?.('icp')"
      >
        <ErrorState
          v-if="icps.list.isError.value"
          :message="
            icps.list.data.value
              ? 'Your ICP definition could not be refreshed. Showing the last received version.'
              : 'Your ICP definition could not be loaded.'
          "
        >
          <Button
            label="Retry ICP definition"
            :disabled="icps.list.isFetching.value"
            @click="icps.list.refetch()"
          />
        </ErrorState>
        <LoadingState
          v-else-if="icps.list.isPending.value"
          message="Loading your ICP definition…"
        />
        <button
          v-for="icp in icps.list.data.value?.items ?? []"
          :key="icp.id"
          type="button"
          class="icp-tile"
          @click="openSettings?.('icp', icp.id)"
        >
          <strong>{{ icp.name }}</strong>
          <span class="icp-description">{{ icpDescription(icp) }}</span>
        </button>
        <p v-if="icpsEmpty" class="placeholder">
          Describe the clients you want, and Huginn will look for them.
        </p>
        <ul v-if="allReactions.length" class="feedback">
          <li v-for="reaction in allReactions" :key="reaction.matchId">
            {{ reaction.kind === 'up' ? 'More like' : 'Less like' }} {{ reaction.companyName
            }}<template v-if="reaction.reason">
              ({{ canonicalFeedbackReason(reaction.reason) }})</template
            >
          </li>
        </ul>
      </ProfileSection>

      <ProfileSection
        title="Leadership"
        add-label="Add a leader"
        add-awaits-backend
        :availability-reason-id="`${availabilityScope}-leaders-unavailable`"
        availability-message="Leader details cannot be saved yet."
      >
        <button
          v-if="ownerName"
          v-bind="awaitingBackendAttrs"
          type="button"
          class="item item--person"
          :aria-describedby="`${availabilityScope}-leaders-unavailable`"
        >
          <span class="person-avatar" aria-hidden="true">{{ initials(ownerName) }}</span>
          <span class="person-copy">
            <span class="item-title">{{ ownerName }}</span>
          </span>
        </button>
      </ProfileSection>

      <ProfileSection
        title="Services"
        :add-label="
          offerings.list.isError.value && !offerings.list.data.value ? undefined : 'Add a service'
        "
        @add="editService()"
      >
        <ErrorState
          v-if="offerings.list.isError.value"
          :message="
            offerings.list.data.value
              ? 'Your services could not be refreshed. Showing the last received list.'
              : 'Your services could not be loaded.'
          "
        >
          <Button
            label="Retry services"
            :disabled="offerings.list.isFetching.value"
            @click="offerings.list.refetch()"
          />
        </ErrorState>
        <LoadingState v-else-if="offerings.list.isPending.value" message="Loading your services…" />
        <button
          v-for="service in offerings.list.data.value?.items ?? []"
          :key="service.id"
          type="button"
          class="item"
          @click="editService(service)"
        >
          <span class="item-title">{{ service.name }}</span>
          <span class="body-text">{{ service.description }}</span>
        </button>
        <p v-if="servicesEmpty" class="placeholder">
          Add what you sell, so Huginn knows who would buy it.
        </p>
        <p
          v-else-if="serviceOffset > 0 && offerings.list.data.value?.items.length === 0"
          class="placeholder"
        >
          No services on this page.
        </p>
        <nav
          v-if="serviceOffset > 0 || offerings.list.data.value?.has_more"
          class="service-pagination"
          aria-label="Service pages"
        >
          <Button
            label="Previous"
            severity="secondary"
            :disabled="serviceOffset === 0"
            @click="serviceOffset = Math.max(0, serviceOffset - servicePageSize)"
          />
          <span>Page {{ Math.floor(serviceOffset / servicePageSize) + 1 }}</span>
          <Button
            label="Next"
            severity="secondary"
            :disabled="offerings.list.isFetching.value || !offerings.list.data.value?.has_more"
            @click="serviceOffset += servicePageSize"
          />
        </nav>
      </ProfileSection>

      <ProfileSection
        title="Clients"
        add-label="Add a client"
        add-awaits-backend
        :availability-reason-id="`${availabilityScope}-clients-unavailable`"
        availability-message="Client details cannot be saved yet."
      >
        <p class="placeholder">Client list is coming soon.</p>
      </ProfileSection>

      <ProfileSection
        title="Links"
        add-label="Add a link"
        add-awaits-backend
        :availability-reason-id="`${availabilityScope}-links-unavailable`"
        availability-message="Link details cannot be saved yet."
      >
        <p class="placeholder">Links are coming soon.</p>
      </ProfileSection>

      <ProfileSection title="Skills">
        <button type="button" class="item" aria-label="Edit skills" @click="editSkills">
          <span v-if="data.skills.length" class="body-text">{{
            data.skills.map((skill) => skill.name).join(' · ')
          }}</span>
          <span v-else class="placeholder">Add your skills.</span>
        </button>
      </ProfileSection>

      <p class="last-edited">
        Professional profile updated {{ new Date(data.updated_at).toLocaleDateString() }}
      </p>
    </template>

    <Dialog
      :visible="editing !== null"
      modal
      :draggable="false"
      :header="dialogTitle"
      :style="{ width: 'min(34rem, calc(100vw - 2rem))' }"
      @update:visible="(visible: boolean) => (visible ? undefined : close())"
    >
      <form class="edit-form" @submit.prevent="submit">
        <template v-if="editing?.kind === 'about'">
          <label for="personal-summary">Professional summary</label>
          <Textarea id="personal-summary" v-model="fields.summary" rows="7" :disabled="pending" />
        </template>
        <template v-else-if="editing?.kind === 'skills'">
          <SkillRows v-model="skills" :disabled="pending" />
        </template>
        <template v-else-if="editing">
          <label for="item-name">Name</label>
          <InputText id="item-name" v-model="fields.name" required />
          <label for="item-description">Description</label>
          <Textarea id="item-description" v-model="fields.description" rows="5" required />
        </template>
        <p v-if="error" class="edit-error" role="alert">{{ error }}</p>
        <div class="edit-actions">
          <Button
            v-if="canDelete && !outcomeUncertain"
            type="button"
            label="Remove"
            severity="danger"
            text
            :disabled="pending"
            @click="removeItem"
          />
          <span class="edit-actions-end">
            <Button
              type="button"
              label="Cancel"
              severity="secondary"
              :disabled="pending"
              @click="close"
            />
            <Button
              v-if="outcomeUncertain"
              type="button"
              :label="editing?.kind === 'service' ? 'Refresh services' : 'Refresh saved profile'"
              :loading="pending"
              @click="editing?.kind === 'service' ? refreshServices() : refreshProfile()"
            />
            <Button v-else type="submit" label="Save" :loading="pending" />
          </span>
        </div>
      </form>
    </Dialog>
  </div>
</template>

<style scoped>
.profile-page {
  width: min(100%, 44rem);
  display: grid;
  gap: var(--space-8);
  margin: 0 auto;
}
.item {
  width: 100%;
  display: grid;
  gap: var(--space-1);
  margin-inline: calc(var(--space-3) * -1);
  padding: var(--space-3);
  box-sizing: content-box;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}
.item:disabled,
.client-row:disabled {
  cursor: not-allowed;
}
.item:not(:disabled):hover {
  background: var(--color-surface-muted);
}
.item-title {
  font-weight: 500;
}
.service-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.item-meta,
.body-text,
.placeholder,
.last-edited {
  color: var(--color-text-muted);
}
.item-meta,
.last-edited {
  font-size: 0.875rem;
}
.body-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.placeholder,
.last-edited {
  margin: 0;
}
.icp-tile {
  width: 100%;
  display: grid;
  gap: var(--space-2);
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}
.icp-tile:hover {
  border-color: var(--color-text-muted);
}
.icp-description {
  font-size: 1.0625rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.item--person {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}
.person-avatar {
  flex: none;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--color-border);
  font-size: 14px;
  font-weight: 600;
}
.person-copy {
  min-width: 0;
  display: grid;
  gap: var(--space-1);
}
.feedback {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding-left: var(--space-5);
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
.last-edited {
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border);
}
.edit-form {
  display: grid;
  gap: var(--space-2);
}
.edit-form > label {
  margin-top: var(--space-2);
  font-weight: 600;
}
.edit-error {
  margin: var(--space-2) 0 0;
  color: var(--color-danger-text);
}
.edit-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-4);
}
.edit-actions-end {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
}
</style>
