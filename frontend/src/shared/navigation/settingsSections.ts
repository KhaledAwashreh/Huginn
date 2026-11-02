import type { InjectionKey } from 'vue';

export type SettingsSection = 'account' | 'icp' | 'security' | 'admin';

// Provided by the app shell so a page can open the settings modal at a section.
export const openSettingsKey: InjectionKey<(section: SettingsSection) => void> =
  Symbol('openSettings');
