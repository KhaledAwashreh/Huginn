import type { RouteRecordRaw } from 'vue-router';
import CreateAccountPage from './pages/CreateAccountPage.vue';
import CheckEmailPage from './pages/CheckEmailPage.vue';
import VerifyEmailPage from './pages/VerifyEmailPage.vue';
import ForgotPasswordPage from './pages/ForgotPasswordPage.vue';
import ResetPasswordPage from './pages/ResetPasswordPage.vue';

export const accountLifecycleRoutes: RouteRecordRaw[] = [
  { path: '/create-account', name: 'create-account', component: CreateAccountPage },
  { path: '/check-email', name: 'check-email', component: CheckEmailPage },
  { path: '/verify-email', name: 'verify-email', component: VerifyEmailPage },
  { path: '/forgot-password', name: 'forgot-password', component: ForgotPasswordPage },
  { path: '/reset-password', name: 'reset-password', component: ResetPasswordPage },
];
