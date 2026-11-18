import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  optimizeDeps: {
    include: ['monaco-editor']
  },
  server: {
    proxy: {
      '/projects': 'http://localhost:8002',
      '/templates': 'http://localhost:8002',
      '/ws': { target: 'ws://localhost:8002', ws: true }
    }
  }
});
