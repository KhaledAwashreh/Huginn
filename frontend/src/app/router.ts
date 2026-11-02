import { configurationRoutes } from '../features/configuration/routes';
import { matchmakingRoutes } from '../features/matchmaking/routes';
import { pipelineRoutes } from '../features/pipeline/routes';
import { accountLifecycleRoutes } from '../features/account-lifecycle/routes';
import { recommendationRoutes } from '../features/recommendations/routes';
import { matchesRoutes } from '../features/matches/routes';
import { profileRoutes } from '../features/profile/routes';
import { createRouter, createWebHistory } from 'vue-router';
import { useSession } from '../features/session/composables/useSession';
import LoginPage from '../features/session/pages/LoginPage.vue';
import AdministrationLayout from './components/AdministrationLayout.vue';
import AdministrationPage from './pages/AdministrationPage.vue';
import PageHeader from '../shared/ui/PageHeader.vue';
import { validateReturnPath } from '../shared/navigation/validateReturnPath';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    // Matches is home; recovery email enrollment now lives in the Security settings.
    { path: '/', name: 'workspace', redirect: '/matches' },
    { path: '/login', name: 'login', component: LoginPage },
    ...accountLifecycleRoutes,
    ...matchesRoutes,
    ...recommendationRoutes,
    ...profileRoutes,
    ...configurationRoutes,
    {
      path: '/admin',
      component: AdministrationLayout,
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        {
          path: '',
          name: 'administration',
          component: AdministrationPage,
          meta: { navigationLabel: 'Administration' },
        },
        ...pipelineRoutes,
        ...matchmakingRoutes,
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: PageHeader,
      props: {
        title: 'Page not found',
        description: 'Use the navigation to return to your workspace.',
      },
      meta: { requiresAuth: true },
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSession();
  if (!session.restored.value) {
    try {
      await session.bootstrap();
    } catch {
      if (to.meta.requiresAuth)
        return { name: 'login', query: { return: validateReturnPath(to.fullPath) } };
    }
  }
  if (to.meta.requiresAuth && !session.isAuthenticated.value)
    return { name: 'login', query: { return: validateReturnPath(to.fullPath) } };
  if (to.name === 'login' && session.isAuthenticated.value)
    return validateReturnPath(to.query.return);
});
