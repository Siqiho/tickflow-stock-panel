import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { ConceptAnalysis } from '@/pages/ConceptAnalysis'

vi.mock('@/lib/useSharedQueries', () => ({
  useSettings: () => ({ data: { is_admin: false } }),
}))

vi.mock('@/components/SectorFundFlowPanel', async () => {
  const actual = await vi.importActual<typeof import('@/components/SectorFundFlowPanel')>('@/components/SectorFundFlowPanel')
  return {
    ...actual,
    SectorFundFlowPanel: () => <div data-testid="concept-fund-flow" />,
    useTopFundFlowName: () => ({ name: '通信技术', mainNet: 1, isLoading: false, hasData: true }),
  }
})

beforeEach(() => {
  vi.spyOn(api, 'extDataList').mockResolvedValue({
    items: [{
      id: 'ext_gn_ths',
      label: '扩展概念',
      mode: 'snapshot',
      fields: [
        { name: 'symbol', dtype: 'string', label: '标的代码' },
        { name: '所属概念', dtype: 'string', label: '所属概念' },
        { name: '股票简称', dtype: 'string', label: '股票简称' },
      ],
      created_at: '2026-07-02T00:00:00',
      updated_at: '2026-07-02T00:00:00',
    }],
  } as never)
  vi.spyOn(api, 'extDataRows').mockResolvedValue({
    id: 'ext_gn_ths',
    label: '扩展概念',
    mode: 'snapshot',
    date: '2026-08-21',
    total: 2,
    limit: 12000,
    fields: [
      { name: 'symbol', dtype: 'string', label: '标的代码' },
      { name: '所属概念', dtype: 'string', label: '所属概念' },
      { name: '股票简称', dtype: 'string', label: '股票简称' },
    ],
    rows: [
      { symbol: '000001.SZ', 所属概念: '金属铝', 股票简称: '平安银行' },
      { symbol: '000002.SZ', 所属概念: '转基因', 股票简称: '万科A' },
    ],
  } as never)
  vi.spyOn(api, 'marketSnapshot').mockResolvedValue({
    as_of: '2026-08-21',
    source: 'quote_snapshot',
    coverage: {
      instrument_rows: 2,
      snapshot_rows: 2,
      priced_rows: 2,
      missing_rows: 0,
      coverage_pct: 100,
      markets: {},
    },
    rows: [
      { symbol: '000001.SZ', name: '平安银行', change_pct: 0.0191, amount: 1_000_000 },
      { symbol: '000002.SZ', name: '万科A', change_pct: -0.0534, amount: 800_000 },
    ],
  } as never)
  vi.spyOn(api, 'fundFlowConcepts').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'fundFlowConceptsRefresh').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'intradayRefresh').mockResolvedValue({ status: 'ok' } as never)
})

afterEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

it('puts an isolated update button on each concept-analysis module', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <ConceptAnalysis />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('概念矩阵')).toBeInTheDocument()
  expect(screen.getAllByText('金属铝').length).toBeGreaterThan(0)
  const updateButtons = screen.getAllByRole('button', { name: '更新' })
  expect(updateButtons).toHaveLength(5)

  const snapshotCalls = vi.mocked(api.marketSnapshot).mock.calls.length
  const rowCalls = vi.mocked(api.extDataRows).mock.calls.length
  fireEvent.click(updateButtons[1])
  await waitFor(() => {
    expect(vi.mocked(api.marketSnapshot).mock.calls.length).toBeGreaterThan(snapshotCalls)
    expect(vi.mocked(api.extDataRows).mock.calls.length).toBeGreaterThan(rowCalls)
  })
  expect(api.fundFlowConceptsRefresh).not.toHaveBeenCalled()
  expect(api.intradayRefresh).not.toHaveBeenCalled()
  expect(await screen.findByText(/已更新 ·/)).toBeInTheDocument()
})
