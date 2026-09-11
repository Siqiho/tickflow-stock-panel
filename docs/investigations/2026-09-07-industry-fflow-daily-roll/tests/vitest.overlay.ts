import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, type Plugin } from 'vitest/config'

const frontend = '/Users/simon/Trading/one-trading/frontend'
const requireFromFrontend = createRequire(path.join(frontend, 'package.json'))
const react = requireFromFrontend('@vitejs/plugin-react')
const isolation = path.resolve(__dirname, '..')
const overlaySrc = path.join(isolation, 'overlay/frontend/src')
const overlayApi = path.join(overlaySrc, 'lib/api.ts')
const overlayPanel = path.join(overlaySrc, 'components/SectorFundFlowPanel.tsx')
const resolvedLog = path.join(isolation, 'results/vitest-resolved-paths.json')
const recorded: Record<string, string> = {}

function recordOverlayResolves(): Plugin {
  const flush = () => {
    fs.mkdirSync(path.dirname(resolvedLog), { recursive: true })
    fs.writeFileSync(
      resolvedLog,
      `${JSON.stringify({ records: recorded, overlayApi, overlayPanel }, null, 2)}\n`,
    )
  }
  return {
    name: 'record-overlay-resolves',
    enforce: 'pre',
    configResolved() {
      recorded['alias:@/lib/api'] = overlayApi
      recorded['alias:@/components/SectorFundFlowPanel'] = overlayPanel
      flush()
    },
    resolveId(source) {
      if (source === 'virtual:overlay-resolves') {
        return '\0virtual:overlay-resolves'
      }
      return undefined
    },
    load(id) {
      if (id === '\0virtual:overlay-resolves') {
        return `export const overlayResolves = ${JSON.stringify({
          '@/lib/api': overlayApi,
          '@/components/SectorFundFlowPanel': overlayPanel,
        })}`
      }
      return undefined
    },
    transform(_code, id) {
      const file = id.split('?')[0]
      if (file === overlayApi) {
        recorded['@/lib/api'] = overlayApi
        flush()
      }
      if (file === overlayPanel) {
        recorded['@/components/SectorFundFlowPanel'] = overlayPanel
        flush()
      }
      return undefined
    },
  }
}

export default defineConfig({
  root: frontend,
  plugins: [recordOverlayResolves(), react()],
  resolve: {
    alias: {
      '@/components/SectorFundFlowPanel': overlayPanel,
      '@/lib/api': overlayApi,
      '@': path.join(frontend, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: [path.join(frontend, 'src/test/setup.ts')],
    include: [path.join(__dirname, 'frontend/**/*.test.tsx')],
    cacheDir: path.join(isolation, '.vitest-cache'),
  },
})
