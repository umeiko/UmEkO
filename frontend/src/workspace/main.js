import { createApp } from 'vue';
import WorkspaceApp from './WorkspaceApp.vue';
import '../shared/theme.css';
import './workspace.css';
import './workbench.css';
import 'highlight.js/styles/github-dark.css';
import '../shared/highlight-light.css';
createApp(WorkspaceApp).mount('#app');

// Template HMR must remount the DOM controller along with its component nodes.
if (import.meta.hot) {
  import.meta.hot.on('vite:beforeUpdate', ({ updates }) => {
    if (updates.some((update) => update.path.startsWith('/src/workspace/'))) location.reload();
  });
}
