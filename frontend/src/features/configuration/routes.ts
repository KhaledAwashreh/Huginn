import type { RouteRecordRaw } from 'vue-router';
import AccountPage from './account/pages/AccountPage.vue';
import ProfessionalProfilePage from './professional-profile/pages/ProfessionalProfilePage.vue';
import ServiceOfferingListPage from './offerings/pages/ServiceOfferingListPage.vue';
import ServiceOfferingEditorPage from './offerings/pages/ServiceOfferingEditorPage.vue';
import IdealClientProfileListPage from './ideal-client-profiles/pages/IdealClientProfileListPage.vue';
import IdealClientProfileEditorPage from './ideal-client-profiles/pages/IdealClientProfileEditorPage.vue';
import DiscoveryStrategyListPage from './discovery-strategies/pages/DiscoveryStrategyListPage.vue';
import DiscoveryStrategyEditorPage from './discovery-strategies/pages/DiscoveryStrategyEditorPage.vue';
export const configurationRoutes: RouteRecordRaw[] = [
  {
    path: '/account',
    name: 'account',
    component: AccountPage,
    meta: { requiresAuth: true, navigationLabel: 'Account' },
  },
  {
    path: '/professional-profile',
    name: 'professional-profile',
    component: ProfessionalProfilePage,
    meta: { requiresAuth: true, navigationLabel: 'Professional profile' },
  },
  {
    path: '/offerings',
    name: 'offerings',
    component: ServiceOfferingListPage,
    meta: { requiresAuth: true, navigationLabel: 'Service offerings' },
  },
  {
    path: '/offerings/new',
    name: 'offering-create',
    component: ServiceOfferingEditorPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/offerings/:id',
    name: 'offering-edit',
    component: ServiceOfferingEditorPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/icps',
    name: 'icps',
    component: IdealClientProfileListPage,
    meta: { requiresAuth: true, navigationLabel: 'ICPs' },
  },
  {
    path: '/icps/new',
    name: 'icp-create',
    component: IdealClientProfileEditorPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/icps/:id',
    name: 'icp-edit',
    component: IdealClientProfileEditorPage,
    meta: { requiresAuth: true },
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
    meta: { requiresAuth: true },
  },
  {
    path: '/strategies/:id',
    name: 'strategy-edit',
    component: DiscoveryStrategyEditorPage,
    meta: { requiresAuth: true },
  },
];
