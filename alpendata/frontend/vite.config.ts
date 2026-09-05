import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';

const cert = process.env.ALPENDATA_DEV_TLS_CERT, key = process.env.ALPENDATA_DEV_TLS_KEY;
if (Boolean(cert) !== Boolean(key)) throw new Error('Set both development TLS certificate and key paths');

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8180' }, ...(cert && key ? { https: { cert: readFileSync(cert), key: readFileSync(key) } } : {}) },
  test: { environment: 'jsdom', environmentOptions: { jsdom: { url: 'https://alpendata.example.test/' } }, globals: true, restoreMocks: true },
});
