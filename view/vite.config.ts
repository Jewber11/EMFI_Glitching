import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  preview: {
    port: 8003,
    proxy: {
      "/api/control": { target: "http://localhost:8001", changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api\/control/, "") },
      "/api/develop": { target: "http://localhost:8002", changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api\/develop/, "") }
    }
  },
  server: {
    port: 8003,
    proxy: {
      '/api/control': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
        rewrite: (p) => p.replace(/^\/api\/control/, '')
      },
      '/api/develop': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        ws: true,
        rewrite: (p) => p.replace(/^\/api\/develop/, '')
      }
    }
  }
});
