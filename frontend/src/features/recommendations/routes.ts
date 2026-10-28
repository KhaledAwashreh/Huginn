import type { RouteRecordRaw } from 'vue-router';
import RecommendationsPage from './pages/RecommendationsPage.vue';
export const recommendationRoutes: RouteRecordRaw[] = [
  {
    path: '/recommendations',
    name: 'recommendations',
    component: RecommendationsPage,
    meta: { requiresAuth: true, navigationLabel: 'Recommendations' },
  },
];
