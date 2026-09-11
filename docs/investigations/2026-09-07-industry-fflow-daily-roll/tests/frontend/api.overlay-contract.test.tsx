import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'

import { api } from '@/lib/api'
import type { FundFlowWindowResponse } from '@/lib/api'
import { overlayResolves } from 'virtual:overlay-resolves'

const mainApi = '/Users/simon/Trading/one-trading/frontend/src/lib/api.ts'
const overlayApi =
  '/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll/overlay/frontend/src/lib/api.ts'
const overlayPanel =
  '/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll/overlay/frontend/src/components/SectorFundFlowPanel.tsx'
const resolvedLog =
  '/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll/results/vitest-resolved-paths.json'

it('resolves overlay api.ts by alias and keeps business freshness fields', () => {
  expect(overlayResolves['@/lib/api']).toBe(overlayApi)
  expect(overlayResolves['@/components/SectorFundFlowPanel']).toBe(overlayPanel)
  const logged = JSON.parse(readFileSync(resolvedLog, 'utf8')) as {
    records: Record<string, string>
  }
  expect(logged.records['@/lib/api']).toBe(overlayApi)

  const overlayDisk = readFileSync(overlayApi, 'utf8')
  const mainDisk = readFileSync(mainApi, 'utf8')
  expect(overlayDisk.includes('INDUSTRY_FFLOW_WINDOW_CONTRACT')).toBe(false)
  expect(overlayDisk.includes("freshness_status?: 'fresh' | 'stale' | 'unknown'")).toBe(true)
  expect(mainDisk.includes('freshness_status?:')).toBe(false)
  expect(typeof api.fundFlowBoardsWindow).toBe('function')

  const sample: FundFlowWindowResponse = {
    ok: true,
    kind: 'board',
    window_days: 5,
    window_label: '近5个交易日累计',
    trading_days: 5,
    snapshot_count: 128,
    covered_count: 128,
    missing_count: 0,
    coverage_pct: 100,
    items: [],
    missing: [],
    prior_available: true,
    data_as_of: '2026-08-31',
    freshness_status: 'fresh',
    freshness_note: '足够新',
    expected_trading_day: '2026-08-31',
    calendar_covers: true,
  }
  expect(sample.freshness_status).toBe('fresh')
  expect(sample.calendar_covers).toBe(true)
})
