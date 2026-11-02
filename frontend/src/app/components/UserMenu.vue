<script setup lang="ts">
import { computed, ref, useId } from 'vue';
import { useRouter } from 'vue-router';
import Menu from 'primevue/menu';
import { LogOut, ShieldCheck, Target, UserRound, Wrench } from '@lucide/vue';
import { ApiError } from '../../api/apiError';
import { useAccount } from '../../features/configuration/account/composables/useAccount';
import { useSession } from '../../features/session/composables/useSession';
import type { SettingsSection } from '../../shared/navigation/settingsSections';

const emit = defineEmits<{ open: [section: SettingsSection] }>();
const session = useSession();
const router = useRouter();
const { account } = useAccount();
const menu = ref<InstanceType<typeof Menu> | null>(null);
const menuId = useId();
const expanded = ref(false);
const signingOut = ref(false);
const message = ref('');

const name = computed(() => {
  const data = account.data.value;
  return data ? `${data.first_name} ${data.last_name}`.trim() : 'Your account';
});
const email = computed(() => account.data.value?.email ?? '');
const initials = computed(() => {
  const data = account.data.value;
  if (!data) return '';
  return `${data.first_name.charAt(0)}${data.last_name.charAt(0)}`.toUpperCase();
});

const items = computed(() => [
  { label: 'Account', lucide: UserRound, command: () => emit('open', 'account') },
  { label: 'ICP definition', lucide: Target, command: () => emit('open', 'icp') },
  { label: 'Security', lucide: ShieldCheck, command: () => emit('open', 'security') },
  ...(session.isAdministrator.value
    ? [{ label: 'Admin', lucide: Wrench, command: () => emit('open', 'admin') }]
    : []),
  { separator: true },
  { label: 'Sign out', lucide: LogOut, command: () => void signOut() },
]);

async function signOut(): Promise<void> {
  if (signingOut.value) return;
  signingOut.value = true;
  message.value = '';
  try {
    await session.logout();
    await router.replace('/login');
  } catch (error) {
    message.value = error instanceof ApiError ? error.message : 'Sign out failed. Try again.';
  } finally {
    signingOut.value = false;
  }
}
</script>

<template>
  <div class="user-menu">
    <button
      type="button"
      class="user-menu-trigger"
      aria-haspopup="true"
      :aria-controls="menuId"
      :aria-expanded="expanded"
      @click="menu?.toggle($event)"
    >
      <span class="avatar" aria-hidden="true">
        <template v-if="initials">{{ initials }}</template>
        <UserRound v-else :size="18" />
      </span>
      <span class="visually-hidden">{{ name }}</span>
    </button>
    <Menu
      :id="menuId"
      ref="menu"
      :model="items"
      popup
      append-to="self"
      class="user-menu-popup"
      @show="expanded = true"
      @hide="expanded = false"
    >
      <template #start>
        <div class="identity">
          <span class="identity-name">{{ name }}</span>
          <span v-if="email" class="identity-email">{{ email }}</span>
        </div>
      </template>
      <template #item="{ item, props }">
        <a v-bind="props.action" class="user-menu-item">
          <component :is="item.lucide" :size="18" :stroke-width="1.75" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </a>
      </template>
    </Menu>
    <p v-if="message" class="user-menu-error" role="alert">{{ message }}</p>
  </div>
</template>

<style scoped>
.user-menu {
  position: relative;
}
.user-menu-trigger {
  display: block;
  padding: 2px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  cursor: pointer;
}
.avatar {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--color-border);
  color: var(--color-text);
  font-size: 13px;
  font-weight: 600;
}
.user-menu-trigger:hover .avatar,
.user-menu-trigger[aria-expanded='true'] .avatar {
  background: var(--color-text-muted);
  color: var(--color-surface);
}
.identity {
  display: grid;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}
.identity-name {
  font-weight: 600;
}
.identity-email {
  color: var(--color-text-muted);
  font-size: 14px;
  overflow-wrap: anywhere;
}
.user-menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.user-menu-item svg {
  color: var(--color-text-muted);
}
.user-menu-error {
  position: absolute;
  top: calc(100% + var(--space-1));
  right: 0;
  width: 14rem;
  margin: 0;
  color: var(--color-danger-text);
  font-size: 14px;
}
</style>

<style>
/* Anchored under the avatar; PrimeVue's computed position assumes a body-level overlay. */
.user-menu .user-menu-popup {
  top: calc(100% + var(--space-1)) !important;
  right: 0 !important;
  left: auto !important;
  inset-inline-start: auto !important;
  margin-top: 0 !important;
  width: 16rem;
}
</style>
