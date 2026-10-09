import type { RouteRecordRaw } from 'vue-router';
import MatchesPage from './pages/MatchesPage.vue';
import MatchDetailPage from './pages/MatchDetailPage.vue';

export const matchesRoutes: RouteRecordRaw[] = [
  {
    path: '/matches',
    name: 'matches',
    component: MatchesPage,
    meta: { requiresAuth: true, navigationLabel: 'Matches' },
  },
  {
    path: '/matches/:id',
    name: 'match-detail',
    component: MatchDetailPage,
    meta: { requiresAuth: true },
  },
];
