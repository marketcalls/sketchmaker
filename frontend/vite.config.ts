import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // No source maps in the shipped bundle: the SPA's files are served without a
    // login, so a .map file would publish the full source tree.
    sourcemap: false,
    rolldownOptions: {
      output: {
        advancedChunks: {
          groups: [
            // React core - rarely changes, cache forever
            { name: 'vendor-react', test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/ },
            { name: 'vendor-ui', test: /node_modules[\\/]@radix-ui[\\/]/ },
            { name: 'vendor-icons', test: /node_modules[\\/]lucide-react[\\/]/ },
            // State management & utilities
            { name: 'vendor-utils', test: /node_modules[\\/](zustand|axios|clsx|tailwind-merge)[\\/]/ },
          ],
        },
      },
    },
    // Increase chunk size warning limit slightly (each chunk should now be smaller)
    chunkSizeWarningLimit: 600,
  },
});
