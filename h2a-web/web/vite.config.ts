import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The FastAPI backend (h2a-web/backend) serves the built app from ../web/dist and
// owns all /api routes. In dev, `vite` proxies /api to the backend on 8733.
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8733', changeOrigin: true },
    },
  },
});
