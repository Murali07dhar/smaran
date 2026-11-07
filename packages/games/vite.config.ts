import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// Demo harness. Content assets are served from the content package as the public dir (assets/... resolves at "/").
export default defineConfig({ plugins: [react()], publicDir: '../content', server: { port: 5180 } });
