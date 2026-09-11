import { createRequire } from 'node:module'
import path from 'node:path'
import { defineConfig } from 'vitest/config'

const frontend = '/Users/simon/Trading/one-trading/frontend'
const requireFromFrontend = createRequire(path.join(frontend, 'package.json'))
const react = requireFromFrontend('@vitejs/plugin-react')
const isolation = path.resolve(__dirname, '..')
const overlaySrc = path.join(isolation, 'overlay/frontend/src')
const review = path.resolve(__dirname)

export default defineConfig({
  root: frontend,
  plugins: [react()],
  resolve: {
    alias: {
      '@/components/SectorFundFlowPanel': path.join(overlaySrc, 'components/SectorFundFlowPanel.tsx'),
      '@': path.join(frontend, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: [path.join(frontend, 'src/test/setup.ts')],
    include: [
      path.join(isolation, 'tests/frontend/SectorFundFlowPanel.industry-freshness.test.tsx'),
    ],
    cacheDir: path.join(review, '.vitest-cache'),
  },
})
