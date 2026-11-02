<script setup lang="ts">
import { computed, inject, ref } from 'vue';
import { ExternalLink, Link as LinkIcon } from '@lucide/vue';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
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
import { useProfessionalProfile } from '../../configuration/professional-profile/composables/useProfessionalProfile';
import { useMatchReactions } from '../../matches/composables/useMatchReactions';
import { matchRejectionReasonLabel } from '../../matches/lib/matchRejectionReasons';
import BusinessCard from '../components/BusinessCard.vue';
import ProfileSection from '../components/ProfileSection.vue';
import {
  useBusinessDetails,
  type ClientReference,
  type Leader,
  type ProfileResource,
} from '../composables/useBusinessDetails';
import {
  engagementDates,
  icpDescription,
  websiteLabel,
  websiteUrl,
} from '../lib/profileFormatting';
import {
  describeServiceMutationFailure,
  type ServiceMutationFailure,
} from '../lib/serviceMutationFailure';

type Editing =
  | { kind: 'business' }
  | { kind: 'about' }
  | { kind: 'skills' }
  | { kind: 'leader'; index: number | null }
  | { kind: 'client'; index: number | null }
  | { kind: 'resource'; index: number | null }
  | { kind: 'service'; id: string | null };

const openSettings = inject(openSettingsKey, null);
const { account } = useAccount();
const { profile, save } = useProfessionalProfile();
const offerings = useServiceOffering();
const icps = useIdealClientProfile();
const { allReactions } = useMatchReactions();
const { details, saveDetails } = useBusinessDetails();

const data = computed(() => profile.data.value);
const businessName = computed(() => details.value.name || 'your business');
// Until leaders are edited, the account holder is the business's founder.
const leaders = computed<Leader[]>(() => {
  if (details.value.leaders.length) return details.value.leaders;
  const owner = account.data.value;
  if (!owner) return [];
  return [
    {
      name: `${owner.first_name} ${owner.last_name}`.trim(),
      role: data.value?.headline ?? '',
      bio: '',
    },
  ];
});
const initials = (name: string) =>
  name
    .split(/\s+/)
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
const clientDates = (client: ClientReference) =>
  engagementDates(client.startMonth ?? '', client.endMonth ?? '', client.current ?? false);
const resourceHref = (resource: ProfileResource) => websiteUrl(resource.url) ?? undefined;
const servicesEmpty = computed(
  () => !offerings.list.isError.value && offerings.list.data.value?.items.length === 0,
);
const icpsEmpty = computed(
  () => !icps.list.isError.value && icps.list.data.value?.items.length === 0,
);

const editing = ref<Editing | null>(null);
const fields = ref<Record<string, string>>({});
const flag = ref(false);
const currentClient = ref(false);
const opened = ref('');
const pending = ref(false);
const error = ref('');
const outcomeUncertain = ref(false);

const snapshot = () => JSON.stringify([fields.value, flag.value, currentClient.value]);
const dialogTitle = computed(() => {
  const current = editing.value;
  if (!current) return '';
  if (current.kind === 'business') return 'Business details';
  if (current.kind === 'about') return `About ${businessName.value}`;
  if (current.kind === 'skills') return 'Skills';
  if (current.kind === 'service') return current.id ? 'Edit service' : 'Add a service';
  if (current.kind === 'leader') return current.index === null ? 'Add a leader' : 'Edit leader';
  if (current.kind === 'client') return current.index === null ? 'Add a client' : 'Edit client';
  return current.index === null ? 'Add a link' : 'Edit link';
});
const canDelete = computed(() => {
  const current = editing.value;
  if (!current) return false;
  if (current.kind === 'service') return current.id !== null;
  if (!('index' in current)) return false;
  if (current.kind === 'leader') return current.index !== null && details.value.leaders.length > 0;
  return current.index !== null;
});

function open(next: Editing, values: Record<string, string>, checked = false): void {
  editing.value = next;
  fields.value = values;
  flag.value = checked;
  opened.value = snapshot();
  error.value = '';
  outcomeUncertain.value = false;
}
function editBusiness(): void {
  const { name, tagline, website, location, practice } = details.value;
  open({ kind: 'business' }, { name, tagline, website, location, practice });
}
function editAbout(): void {
  open({ kind: 'about' }, { summary: data.value?.professional_summary ?? '' });
}
function editSkills(): void {
  open(
    { kind: 'skills' },
    { skills: (data.value?.skills ?? []).map((skill) => skill.name).join(', ') },
  );
}
function editLeader(index: number | null): void {
  const item = index === null ? undefined : leaders.value[index];
  open(
    { kind: 'leader', index },
    { name: item?.name ?? '', role: item?.role ?? '', bio: item?.bio ?? '' },
  );
}
function editClient(index: number | null): void {
  const item = index === null ? undefined : details.value.clients[index];
  currentClient.value = item?.current ?? false;
  open(
    { kind: 'client', index },
    {
      name: item?.name ?? '',
      role: item?.role ?? '',
      location: item?.location ?? '',
      startMonth: item?.startMonth ?? '',
      endMonth: item?.endMonth ?? '',
      work: item?.work ?? '',
      industry: item?.industry ?? '',
      stage: item?.stage ?? '',
      size: item?.size ?? '',
    },
    item?.idealExample ?? false,
  );
}
function editResource(index: number | null): void {
  const item = index === null ? undefined : details.value.resources[index];
  open({ kind: 'resource', index }, { title: item?.title ?? '', url: item?.url ?? '' });
}
function editService(service?: { id: string; name: string; description: string }): void {
  open(
    { kind: 'service', id: service?.id ?? null },
    { name: service?.name ?? '', description: service?.description ?? '' },
  );
}

function close(): void {
  if (pending.value) return;
  if (snapshot() !== opened.value && !window.confirm('Discard your unsaved changes?')) return;
  editing.value = null;
}
function replaced<T>(items: readonly T[], index: number | null, item: T): T[] {
  return index === null ? [...items, item] : items.map((old, at) => (at === index ? item : old));
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
  outcomeUncertain.value = false;
  error.value = '';
  editing.value = null;
}

async function submit(): Promise<void> {
  const current = editing.value;
  const profileData = data.value;
  if (!current || !profileData || pending.value || outcomeUncertain.value) return;
  const value = fields.value;
  const describeFailure =
    current.kind === 'service' ? describeServiceMutationFailure : generalFailure;
  await persist(async () => {
    if (current.kind === 'business') {
      saveDetails({
        name: (value.name ?? '').trim(),
        tagline: (value.tagline ?? '').trim(),
        website: (value.website ?? '').trim(),
        location: (value.location ?? '').trim(),
        practice: (value.practice ?? '').trim(),
      });
    } else if (current.kind === 'about') {
      await save.mutateAsync({ professional_summary: (value.summary ?? '').trim() || null });
    } else if (current.kind === 'skills') {
      const skills = (value.skills ?? '')
        .split(/[,\n]/)
        .map((name) => ({ name: name.trim() }))
        .filter((skill) => skill.name);
      await save.mutateAsync({ skills });
    } else if (current.kind === 'leader') {
      saveDetails({
        leaders: replaced(leaders.value, current.index, {
          name: (value.name ?? '').trim(),
          role: (value.role ?? '').trim(),
          bio: (value.bio ?? '').trim(),
        }),
      });
    } else if (current.kind === 'client') {
      saveDetails({
        clients: replaced(details.value.clients, current.index, {
          name: (value.name ?? '').trim(),
          role: (value.role ?? '').trim(),
          startMonth: value.startMonth ?? '',
          endMonth: currentClient.value ? '' : (value.endMonth ?? ''),
          current: currentClient.value,
          work: (value.work ?? '').trim(),
          industry: (value.industry ?? '').trim(),
          stage: (value.stage ?? '').trim(),
          size: (value.size ?? '').trim(),
          location: (value.location ?? '').trim(),
          idealExample: flag.value,
        }),
      });
    } else if (current.kind === 'resource') {
      const previous = current.index === null ? undefined : details.value.resources[current.index];
      const url = (value.url ?? '').trim();
      if (!websiteUrl(url)) throw new Error('Add a valid link.');
      saveDetails({
        resources: replaced(details.value.resources, current.index, {
          id: previous?.id ?? crypto.randomUUID(),
          title: (value.title ?? '').trim() || websiteLabel(url),
          url,
        }),
      });
    } else {
      const body = {
        name: (value.name ?? '').trim(),
        description: (value.description ?? '').trim(),
      };
      if (current.id) await offerings.update.mutateAsync({ id: current.id, body });
      else await offerings.create.mutateAsync(body);
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
    if (current.kind === 'leader') {
      saveDetails({ leaders: details.value.leaders.filter((_, at) => at !== current.index) });
    } else if (current.kind === 'client') {
      saveDetails({ clients: details.value.clients.filter((_, at) => at !== current.index) });
    } else if (current.kind === 'resource') {
      saveDetails({ resources: details.value.resources.filter((_, at) => at !== current.index) });
    } else if (current.kind === 'service' && current.id) {
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
      <BusinessCard :business="details" @edit="editBusiness" />

      <ProfileSection :title="`About ${businessName}`">
        <button type="button" class="item" aria-label="Edit about your business" @click="editAbout">
          <span v-if="data.professional_summary" class="body-text">{{
            data.professional_summary
          }}</span>
          <span v-else class="placeholder">Describe your business in a few sentences.</span>
        </button>
      </ProfileSection>

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
          @click="openSettings?.('icp')"
        >
          <span class="icp-description">{{ icpDescription(icp) }}</span>
        </button>
        <p v-if="icpsEmpty" class="placeholder">
          Describe the clients you want, and Huginn will look for them.
        </p>
        <ul v-if="allReactions.length" class="feedback">
          <li v-for="reaction in allReactions" :key="reaction.matchId">
            {{ reaction.kind === 'up' ? 'More like' : 'Less like' }} {{ reaction.companyName
            }}<template v-if="reaction.reason">
              ({{ matchRejectionReasonLabel(reaction.reason) }})</template
            >
          </li>
        </ul>
      </ProfileSection>

      <ProfileSection
        title="Leadership"
        add-label="Add a leader"
        add-awaits-backend
        @add="editLeader(null)"
      >
        <button
          v-for="(leader, index) in leaders"
          v-bind="awaitingBackendAttrs"
          :key="`${leader.name}-${index}`"
          type="button"
          class="item item--person"
          @click="editLeader(index)"
        >
          <span class="person-avatar" aria-hidden="true">{{ initials(leader.name) }}</span>
          <span class="person-copy">
            <span class="item-title">{{ leader.name }}</span>
            <span v-if="leader.role" class="item-meta">{{ leader.role }}</span>
            <span v-if="leader.bio" class="body-text">{{ leader.bio }}</span>
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
      </ProfileSection>

      <ProfileSection
        title="Clients"
        add-label="Add a client"
        add-awaits-backend
        @add="editClient(null)"
      >
        <div v-if="details.clients.length" class="client-list">
          <button
            v-for="(client, index) in details.clients"
            v-bind="awaitingBackendAttrs"
            :key="`${client.name}-${index}`"
            type="button"
            class="client-row"
            @click="editClient(index)"
          >
            <span class="client-logo" aria-hidden="true">{{ client.name.charAt(0) }}</span>
            <span class="client-copy">
              <span class="item-title">{{ client.name }}</span>
              <span v-if="client.role" class="client-line">{{ client.role }}</span>
              <span v-if="clientDates(client)" class="client-line">{{ clientDates(client) }}</span>
            </span>
            <span v-if="client.idealExample" class="client-tag">Ideal client</span>
          </button>
        </div>
        <p v-else class="placeholder">Client list is coming soon.</p>
      </ProfileSection>

      <ProfileSection
        title="Links"
        add-label="Add a link"
        add-awaits-backend
        @add="editResource(null)"
      >
        <div v-for="(resource, index) in details.resources" :key="resource.id" class="resource">
          <button
            v-bind="awaitingBackendAttrs"
            type="button"
            class="item item--resource"
            @click="editResource(index)"
          >
            <LinkIcon :size="18" aria-hidden="true" />
            <span class="item-title">{{ resource.title }}</span>
          </button>
          <a
            v-if="resourceHref(resource)"
            class="resource-open"
            :href="resourceHref(resource)"
            target="_blank"
            rel="noopener noreferrer"
            :aria-label="`Open ${resource.title}`"
            ><ExternalLink :size="16" aria-hidden="true"
          /></a>
        </div>
        <p v-if="!details.resources.length" class="placeholder">Links are coming soon.</p>
      </ProfileSection>

      <ProfileSection title="Skills">
        <button type="button" class="item" aria-label="Edit skills" @click="editSkills">
          <span v-if="data.skills.length" class="body-text">{{
            data.skills.map((skill) => skill.name).join(' · ')
          }}</span>
          <span v-else class="placeholder">Add your skills.</span>
        </button>
      </ProfileSection>

      <p class="last-edited">Last edited {{ new Date(data.updated_at).toLocaleDateString() }}</p>
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
        <template v-if="editing?.kind === 'business'">
          <label for="business-name">Business name</label>
          <InputText id="business-name" v-model="fields.name" />
          <label for="business-tagline">Tagline</label>
          <InputText id="business-tagline" v-model="fields.tagline" />
          <label for="business-website">Website</label>
          <InputText id="business-website" v-model="fields.website" />
          <label for="business-location">Location</label>
          <InputText id="business-location" v-model="fields.location" />
          <label for="business-practice">Type of practice</label>
          <InputText id="business-practice" v-model="fields.practice" placeholder="Solo practice" />
        </template>
        <template v-else-if="editing?.kind === 'about'">
          <label for="about-summary">Summary</label>
          <Textarea id="about-summary" v-model="fields.summary" rows="7" />
        </template>
        <template v-else-if="editing?.kind === 'skills'">
          <label for="skills-list">Skills, separated by commas</label>
          <Textarea id="skills-list" v-model="fields.skills" rows="5" />
        </template>
        <template v-else-if="editing?.kind === 'leader'">
          <label for="leader-name">Name</label>
          <InputText id="leader-name" v-model="fields.name" required />
          <label for="leader-role">Role</label>
          <InputText id="leader-role" v-model="fields.role" />
          <label for="leader-bio">Short bio</label>
          <Textarea id="leader-bio" v-model="fields.bio" rows="4" />
        </template>
        <template v-else-if="editing?.kind === 'client'">
          <label for="client-name">Client name <span aria-hidden="true">*</span></label>
          <InputText id="client-name" v-model="fields.name" required />
          <label for="client-role">Your role</label>
          <InputText
            id="client-role"
            v-model="fields.role"
            placeholder="Fractional Head of Design"
          />
          <label for="client-location">Location</label>
          <InputText id="client-location" v-model="fields.location" />
          <div class="field-pair">
            <span class="field-stack">
              <label for="client-start">Start month</label>
              <InputText id="client-start" v-model="fields.startMonth" type="month" />
            </span>
            <span v-if="!currentClient" class="field-stack">
              <label for="client-end">End month</label>
              <InputText id="client-end" v-model="fields.endMonth" type="month" />
            </span>
          </div>
          <div class="checkbox-row">
            <Checkbox v-model="currentClient" input-id="client-current" binary />
            <label for="client-current">I currently work with them</label>
          </div>
          <label for="client-work">What you did for them</label>
          <Textarea
            id="client-work"
            v-model="fields.work"
            rows="4"
            maxlength="2000"
            aria-describedby="client-work-help"
            placeholder="Built their design system from scratch"
          />
          <small id="client-work-help" class="field-note"
            >One per line. Huginn can use these as examples when finding matches.
            {{ (fields.work ?? '').length }} / 2000 characters</small
          >
          <label for="client-industry">Industry</label>
          <InputText id="client-industry" v-model="fields.industry" />
          <div class="field-pair">
            <span class="field-stack">
              <label for="client-stage">Stage</label>
              <InputText id="client-stage" v-model="fields.stage" placeholder="Series A" />
            </span>
            <span class="field-stack">
              <label for="client-size">Company size</label>
              <InputText id="client-size" v-model="fields.size" />
            </span>
          </div>
          <div class="checkbox-row">
            <Checkbox v-model="flag" input-id="client-ideal" binary />
            <label for="client-ideal">This is the kind of client I want more of</label>
          </div>
        </template>
        <template v-else-if="editing?.kind === 'resource'">
          <label for="resource-title">Title</label>
          <InputText id="resource-title" v-model="fields.title" />
          <label for="resource-url">Link</label>
          <InputText id="resource-url" v-model="fields.url" placeholder="https://" />
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
              label="Refresh services"
              :loading="pending"
              @click="refreshServices"
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
.client-list {
  display: grid;
  gap: var(--space-1);
}
.client-row {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  padding: var(--space-3);
  margin-inline: calc(var(--space-3) * -1);
  box-sizing: content-box;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}
.client-row:not(:disabled):hover {
  background: var(--color-surface-muted);
}
.client-logo {
  flex: none;
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  font-weight: 650;
}
.client-copy {
  min-width: 0;
  flex: 1;
  display: grid;
}
.client-line {
  color: var(--color-text-muted);
  overflow-wrap: anywhere;
}
.field-pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr));
  gap: var(--space-3);
}
.field-stack {
  min-width: 0;
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.field-stack label {
  font-weight: 600;
}
.client-tag {
  flex: none;
  padding: 2px var(--space-2);
  border: 1px solid var(--color-success-border);
  border-radius: 999px;
  background: var(--color-success-surface);
  color: var(--color-success-text);
  font-size: 0.8125rem;
}
.resource {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.item--resource {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--color-text);
}
.item--resource svg {
  flex: none;
  color: var(--color-text-muted);
}
.resource-open {
  flex: none;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-control);
  color: var(--color-text-muted);
}
.resource-open:hover {
  background: var(--color-surface-muted);
}
.field-note {
  color: var(--color-text-muted);
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
.checkbox-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
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
