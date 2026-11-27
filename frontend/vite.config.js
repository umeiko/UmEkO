import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), '');
  return {
    plugins: [vue()],
    base: './',
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rolldownOptions: {
        input: {
          workspace: fileURLToPath(new URL('./index.html', import.meta.url)),
          admin: fileURLToPath(new URL('./admin.html', import.meta.url)),
        },
      },
    },
    server: {
      proxy: {
        '/v1': env.UMEKO_DEV_API_TARGET || 'http://127.0.0.1:8000',
        '^/admin/': env.UMEKO_DEV_ADMIN_TARGET || 'http://127.0.0.1:9000',
        '/guide': env.UMEKO_DEV_API_TARGET || 'http://127.0.0.1:8000',
      },
    },
  };
});
