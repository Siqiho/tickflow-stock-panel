import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import type { IncomingMessage } from 'node:http'
import type { ClientRequest } from 'node:http'
import path from 'node:path'

const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:3018'

const apiProxy = {
  '/api': {
    target: apiTarget,
    configure: (proxy: { on: (event: 'proxyReq', listener: (proxyReq: ClientRequest, req: IncomingMessage) => void) => void }) => {
      proxy.on('proxyReq', (_proxyReq, req) => {
        if (req.url?.includes('/stream')) {
          _proxyReq.setHeader('Accept', 'text/event-stream')
          _proxyReq.setHeader('Cache-Control', 'no-cache')
          _proxyReq.setHeader('Connection', 'keep-alive')
        }
      })
    },
  },
  '/health': apiTarget,
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3011,
    proxy: apiProxy,
  },
  preview: {
    host: '127.0.0.1',
    port: 3011,
    proxy: apiProxy,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
