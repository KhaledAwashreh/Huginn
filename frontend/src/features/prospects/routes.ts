import type { RouteRecordRaw } from 'vue-router';
import ProspectsPage from './pages/ProspectsPage.vue';

export const prospectRoutes: RouteRecordRaw[] = [
  {
    path: '/prospects',
    name: 'prospects',
    component: ProspectsPage,
    meta: { requiresAuth: true, navigationLabel: 'Prospects' },
  },
];
