import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  base: '/',
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8766',
        timeout: 0,
      },
      '/health': 'http://127.0.0.1:8766',
      '/view': 'http://127.0.0.1:8766',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Split vendors so the production JS can be uploaded in pieces
        // (GitHub MCP file commits are unreliable above ~80–100k).
        manualChunks(id) {
          if (id.includes('node_modules/svelte') || id.includes('node_modules/@sveltejs')) {
            return 'svelte';
          }
          if (id.includes('node_modules')) {
            return 'vendor';
          }
        },
      },
    },
  },
  test: {
    environment: 'node',
  },
});
