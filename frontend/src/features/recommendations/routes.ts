import type { RouteRecordRaw } from 'vue-router';
import RecommendationsPage from './pages/RecommendationsPage.vue';
export const recommendationRoutes: RouteRecordRaw[] = [
  {
    path: '/weekly-matches',
    name: 'weekly-matches',
    redirect: '/recommendations',
    meta: { requiresAuth: true },
  },
  {
    path: '/recommendations',
    name: 'recommendations',
    component: RecommendationsPage,
    meta: { requiresAuth: true, navigationLabel: 'Recommendations' },
  },
];
