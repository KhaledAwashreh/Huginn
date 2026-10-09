import type { RouteRecordRaw } from 'vue-router';
import MatchmakingHistoryPage from './pages/MatchmakingHistoryPage.vue';
import MatchmakingRunPage from './pages/MatchmakingRunPage.vue';

export const matchmakingRoutes: RouteRecordRaw[] = [
  {
    path: '/admin/matchmaking',
    name: 'admin-matchmaking-history',
    component: MatchmakingHistoryPage,
    meta: { requiresAuth: true, requiresAdmin: true, navigationLabel: 'Matchmaking' },
  },
  {
    path: '/admin/matchmaking/runs/:id',
    name: 'admin-matchmaking-run',
    component: MatchmakingRunPage,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
];
