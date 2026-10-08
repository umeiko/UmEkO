import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: fileURLToPath(new URL('../umeko/server/static/ui', import.meta.url)),
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        workspace: fileURLToPath(new URL('./index.html', import.meta.url)),
        admin: fileURLToPath(new URL('./admin.html', import.meta.url)),
      },
    },
  },
  server: { proxy: { '/v1': 'http://127.0.0.1:8000', '^/admin/': 'http://127.0.0.1:9000' } },
});
