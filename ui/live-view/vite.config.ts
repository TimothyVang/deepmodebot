import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

// One self-contained HTML file: the live view server serves it as-is, with no network fetches but Mermaid.
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  build: { outDir: path.resolve(__dirname, '../../plugins/deepmodebot/skills/deepmodebot/assets/live-view'), emptyOutDir: false, rollupOptions: { input: 'viewer.html' } },
  server: { proxy: { '/agui': 'http://127.0.0.1:' + (process.env.LIVE_VIEW_PORT ?? '0'), '/health': 'http://127.0.0.1:' + (process.env.LIVE_VIEW_PORT ?? '0') } },
});
