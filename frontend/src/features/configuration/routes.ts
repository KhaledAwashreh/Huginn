import type { RouteRecordRaw } from 'vue-router';
import AccountPage from './account/pages/AccountPage.vue';
import ProfessionalProfilePage from './professional-profile/pages/ProfessionalProfilePage.vue';
import ServiceOfferingListPage from './offerings/pages/ServiceOfferingListPage.vue';
import ServiceOfferingEditorPage from './offerings/pages/ServiceOfferingEditorPage.vue';
import DiscoveryStrategyListPage from './discovery-strategies/pages/DiscoveryStrategyListPage.vue';
import DiscoveryStrategyEditorPage from './discovery-strategies/pages/DiscoveryStrategyEditorPage.vue';
export const configurationRoutes: RouteRecordRaw[] = [
  {
    path: '/account',
    name: 'account',
    component: AccountPage,
    meta: { requiresAuth: true, navigationLabel: 'Account' },
  },
  // Full forms and lists behind the readable profile, until its dialogs replace them.
  {
    path: '/professional-profile',
    name: 'professional-profile',
    component: ProfessionalProfilePage,
    meta: { requiresAuth: true, breadcrumbs: [{ label: 'Profile', to: '/profile' }] },
  },
  {
    path: '/offerings',
    name: 'offerings',
    component: ServiceOfferingListPage,
    meta: { requiresAuth: true, breadcrumbs: [{ label: 'Profile', to: '/profile' }] },
  },
  {
    path: '/offerings/new',
    name: 'offering-create',
    component: ServiceOfferingEditorPage,
    meta: {
      requiresAuth: true,
      breadcrumbs: [
        { label: 'Profile', to: '/profile' },
        { label: 'Services', to: '/offerings' },
      ],
    },
  },
  {
    path: '/offerings/:id',
    name: 'offering-edit',
    component: ServiceOfferingEditorPage,
    meta: {
      requiresAuth: true,
      breadcrumbs: [
        { label: 'Profile', to: '/profile' },
        { label: 'Services', to: '/offerings' },
      ],
    },
  },
  {
    path: '/strategies',
    name: 'strategies',
    component: DiscoveryStrategyListPage,
    meta: { requiresAuth: true, navigationLabel: 'Discovery strategies' },
  },
  {
    path: '/strategies/new',
    name: 'strategy-create',
    component: DiscoveryStrategyEditorPage,
    meta: {
      requiresAuth: true,
      breadcrumbs: [{ label: 'Discovery strategies', to: '/strategies' }],
    },
  },
  {
    path: '/strategies/:id',
    name: 'strategy-edit',
    component: DiscoveryStrategyEditorPage,
    meta: {
      requiresAuth: true,
      breadcrumbs: [{ label: 'Discovery strategies', to: '/strategies' }],
    },
  },
];
