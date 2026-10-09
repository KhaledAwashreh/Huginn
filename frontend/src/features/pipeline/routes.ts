import type { RouteRecordRaw } from 'vue-router';
import PipelineHistoryPage from './pages/PipelineHistoryPage.vue';
import PipelineInvocationPage from './pages/PipelineInvocationPage.vue';

export const pipelineRoutes: RouteRecordRaw[] = [
  {
    path: '/admin/pipeline',
    name: 'admin-pipeline-history',
    component: PipelineHistoryPage,
    meta: { requiresAuth: true, requiresAdmin: true, navigationLabel: 'Data collection' },
  },
  {
    path: '/admin/pipeline/invocations/:id',
    name: 'admin-pipeline-invocation',
    component: PipelineInvocationPage,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
];
