<script setup lang="ts">
import { computed, ref, type Component } from 'vue';
import { useRouter } from 'vue-router';
import Dialog from 'primevue/dialog';
import Button from 'primevue/button';
import { ShieldCheck, Target, UserRound, Wrench, X } from '@lucide/vue';
import AccountForm from '../../features/configuration/account/components/AccountForm.vue';
import IcpDefinitionPanel from '../../features/configuration/ideal-client-profiles/components/IcpDefinitionPanel.vue';
import AccountSecurityPanel from '../../features/configuration/account/components/AccountSecurityPanel.vue';
import { useAccount } from '../../features/configuration/account/composables/useAccount';
import { useMatchReactions } from '../../features/matches/composables/useMatchReactions';
import { matchRejectionReasonLabel } from '../../features/matches/lib/matchRejectionReasons';
import { useBusinessDetails } from '../../features/profile/composables/useBusinessDetails';
import { useSession } from '../../features/session/composables/useSession';
import LoadingState from '../../shared/ui/LoadingState.vue';
import ErrorState from '../../shared/ui/ErrorState.vue';
import type { SettingsSection } from '../../shared/navigation/settingsSections';

type SectionOption = {
  value: SettingsSection;
  label: string;
  description: string;
  icon: Component;
};

const visible = defineModel<boolean>('visible', { required: true });
const section = defineModel<SettingsSection>('section', { required: true });
const session = useSession();
const router = useRouter();
const { account } = useAccount();
const { allReactions } = useMatchReactions();
const { details } = useBusinessDetails();
const icpFeedback = computed(() =>
  allReactions.value.map((reaction) => ({
    ...reaction,
    reasonLabel: reaction.reason ? matchRejectionReasonLabel(reaction.reason) : null,
  })),
);
const accountForm = ref<InstanceType<typeof AccountForm> | null>(null);
const icpPanel = ref<InstanceType<typeof IcpDefinitionPanel> | null>(null);

const sections = computed<SectionOption[]>(() => [
  {
    value: 'account',
    label: 'Account',
    description: 'Your name and the contact details Huginn uses.',
    icon: UserRound,
  },
  {
    value: 'icp',
    label: 'ICP definition',
    description: 'Who Huginn looks for on your behalf, and what has shaped it.',
    icon: Target,
  },
  {
    value: 'security',
    label: 'Security',
    description: 'Your password and how you recover your account.',
    icon: ShieldCheck,
  },
  ...(session.isAdministrator.value
    ? [
        {
          value: 'admin' as const,
          label: 'Admin',
          description: 'Collect company data and run matchmaking.',
          icon: Wrench,
        },
      ]
    : []),
]);
const current = computed(
  // Account is always listed; it is the fallback if admin access is removed while open.
  () =>
    sections.value.find((option) => option.value === section.value) ??
    (sections.value[0] as SectionOption),
);
const adminTools = [
  {
    title: 'Data collection',
    description:
      'Start the existing collection pipeline, follow its progress, and inspect saved results.',
    label: 'Open data collection',
    to: '/admin/pipeline',
  },
  {
    title: 'Matchmaking',
    description:
      'Trigger the matching service for a specific user or all eligible users, then review run outcomes.',
    label: 'Open matchmaking',
    to: '/admin/matchmaking',
  },
];

async function canLeaveSection(): Promise<boolean> {
  const form = accountForm.value ?? icpPanel.value;
  return form ? await form.canClose() : true;
}

async function select(next: SettingsSection): Promise<void> {
  if (next === section.value || !(await canLeaveSection())) return;
  section.value = next;
}

async function close(): Promise<void> {
  if (await canLeaveSection()) visible.value = false;
}

// Admin tools are full pages with their own run history, so they open behind the dialog.
async function openAdminTool(path: string): Promise<void> {
  visible.value = false;
  await router.push(path);
}
</script>

<template>
  <Dialog
    :visible="visible"
    modal
    :show-header="false"
    :draggable="false"
    class="settings-dialog"
    :pt="{
      root: { 'aria-labelledby': 'settings-title' },
      content: { class: 'settings-dialog-content' },
    }"
    @update:visible="(next: boolean) => (next ? (visible = true) : void close())"
  >
    <div class="settings">
      <nav class="settings-nav" aria-label="Settings sections">
        <button
          v-for="option in sections"
          :key="option.value"
          type="button"
          :class="['settings-nav-item', { 'settings-nav-item-active': option.value === section }]"
          :aria-current="option.value === section ? 'page' : undefined"
          @click="select(option.value)"
        >
          <component :is="option.icon" :size="20" :stroke-width="1.75" aria-hidden="true" />
          <span>{{ option.label }}</span>
        </button>
      </nav>

      <section class="settings-panel">
        <header class="settings-header">
          <div>
            <h2 id="settings-title">{{ current.label }}</h2>
            <p>{{ current.description }}</p>
          </div>
          <button type="button" class="settings-close" aria-label="Close settings" @click="close">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>

        <div class="settings-body">
          <template v-if="current.value === 'account'">
            <LoadingState
              v-if="account.isPending.value && !account.data.value"
              message="Loading account…"
            />
            <ErrorState
              v-else-if="account.isError.value && !account.data.value"
              message="Account details could not be loaded. Reload before trying again."
            />
            <AccountForm
              v-else-if="account.data.value"
              ref="accountForm"
              :account="account.data.value"
            />
          </template>
          <IcpDefinitionPanel
            v-else-if="current.value === 'icp'"
            ref="icpPanel"
            :clients="details.clients"
            :reactions="icpFeedback"
          />
          <AccountSecurityPanel v-else-if="current.value === 'security'" />
          <div v-else class="admin-tools">
            <article v-for="tool in adminTools" :key="tool.to" class="admin-tool">
              <h3>{{ tool.title }}</h3>
              <p>{{ tool.description }}</p>
              <Button :label="tool.label" severity="secondary" @click="openAdminTool(tool.to)" />
            </article>
          </div>
        </div>
      </section>
    </div>
  </Dialog>
</template>

<style scoped>
.settings {
  height: min(44rem, 85vh);
  display: grid;
  grid-template-columns: 15rem minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
}
.settings-nav {
  display: grid;
  align-content: start;
  gap: var(--space-1);
  padding: var(--space-4);
  border-right: 1px solid var(--color-border);
  background: var(--color-surface-muted);
}
.settings-nav-item {
  min-height: 42px;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-3);
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}
.settings-nav-item svg {
  color: var(--color-text-muted);
}
.settings-nav-item:hover {
  background: var(--color-border);
}
.settings-nav-item-active {
  background: var(--color-border);
  font-weight: 600;
}
.settings-nav-item-active svg {
  color: var(--color-text);
}
.settings-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.settings-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-6) var(--space-6) var(--space-4);
}
.settings-header h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 650;
  line-height: 1.25;
}
.settings-header p {
  margin: var(--space-2) 0 0;
  color: var(--color-text-muted);
}
.settings-close {
  flex: none;
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}
.settings-close:hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}
.settings-body {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--space-6) var(--space-6);
}
.admin-tools {
  display: grid;
  gap: var(--space-4);
}
.admin-tool {
  display: grid;
  justify-items: start;
  gap: var(--space-2);
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
}
.admin-tool h3,
.admin-tool p {
  margin: 0;
}
.admin-tool p {
  color: var(--color-text-muted);
}

@media (max-width: 699px) {
  .settings {
    height: 85vh;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
  }
  .settings-nav {
    display: flex;
    overflow-x: auto;
    padding: var(--space-2);
    border-right: 0;
    border-bottom: 1px solid var(--color-border);
  }
  .settings-nav-item {
    flex: none;
  }
  .settings-header {
    padding: var(--space-4);
  }
  .settings-body {
    padding: 0 var(--space-4) var(--space-4);
  }
}
</style>

<style>
.settings-dialog {
  width: min(64rem, calc(100vw - 2rem));
  overflow: hidden;
}
.settings-dialog .settings-dialog-content {
  padding: 0;
  overflow: hidden;
}
</style>
