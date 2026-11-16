import type { InjectionKey, Ref } from 'vue';

export type Breadcrumb = { label: string; to: string };

declare module 'vue-router' {
  interface RouteMeta {
    // Parent pages shown before the title in the top bar, outermost first.
    breadcrumbs?: Breadcrumb[];
    // The top navigation already names this page, so its title is for screen readers only.
    hideTitle?: boolean;
  }
}

export type PageTitle = { owner: symbol; title: string };

// Provided by the app shell so each page's PageHeader can show its title in the top bar.
export const pageTitleKey: InjectionKey<Ref<PageTitle | null>> = Symbol('pageTitle');
