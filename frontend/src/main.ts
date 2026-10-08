import { createApp } from 'vue';
import { VueQueryPlugin } from '@tanstack/vue-query';
import PrimeVue from 'primevue/config';
import App from './app/App.vue';
import { router } from './app/router';
import { queryClient } from './app/queryClient';
import { huginnPreset } from './shared/theme/preset';
import './shared/theme/tokens.css';

createApp(App)
  .use(PrimeVue, { theme: { preset: huginnPreset, options: { darkModeSelector: false } } })
  .use(VueQueryPlugin, { queryClient })
  .use(router)
  .mount('#app');
