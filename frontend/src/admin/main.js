import { createApp } from 'vue';
import AdminApp from './AdminApp.vue';
import '../shared/theme.css';
import 'highlight.js/styles/github-dark.css';
import '../shared/highlight-light.css';
import '../shared/markdown.css';
createApp(AdminApp).mount('#app');
