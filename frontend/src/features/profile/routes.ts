import type { RouteRecordRaw } from 'vue-router';
import ProfilePage from './pages/ProfilePage.vue';

export const profileRoutes: RouteRecordRaw[] = [
  {
    path: '/profile',
    name: 'profile',
    component: ProfilePage,
    meta: { requiresAuth: true, navigationLabel: 'Profile', hideTitle: true },
  },
];
