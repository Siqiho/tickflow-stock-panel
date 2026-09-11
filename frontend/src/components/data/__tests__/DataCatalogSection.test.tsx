import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { CoverageBar } from '../CoverageBar'
import { DataCatalogSection } from '../DataCatalogSection'
import { DatasetCatalogCard } from '../DatasetCatalogCard'
import { catalogFixture, makeEntry } from './catalogFixtures'

function renderCatalog(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  return {
    client,
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('catalog presentation', () => {
  it('keeps stale data visible, shows ETF and all five financial tables', () => {
    render(<DataCatalogSection catalog={catalogFixture} isStale error={new Error('offline')} />)

    expect(screen.getByText('状态可能过期')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'ETF daily bars' })).toBeInTheDocument()
    const finance = screen.getByRole('region', { name: '财务数据' })
    for (const title of [
      'Financial metrics',
      'Income statements',
      'Balance sheets',
      'Cash-flow statements',
      'Shares outstanding',
    ]) {
      expect(within(finance).getByRole('heading', { name: title })).toBeInTheDocument()
    }
  })

  it('uses honest sealed-L1 wording and only shows depth5 when explicitly available', () => {
    const { rerender } = render(<DataCatalogSection catalog={catalogFixture} />)

    expect(screen.getByRole('heading', { name: '封板 L1' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Five-level order book' })).not.toBeInTheDocument()

    const depth5Available = {
      ...catalogFixture,
      datasets: catalogFixture.datasets.map((entry) => (
        entry.descriptor.dataset_id === 'depth5' ? { ...entry, depth5_available: true } : entry
      )),
    }
    rerender(<DataCatalogSection catalog={depth5Available} />)
    expect(screen.getByRole('heading', { name: 'Five-level order book' })).toBeInTheDocument()
  })

  it('renders trading calendar under reference group', () => {
    render(<DataCatalogSection catalog={catalogFixture} />)
    const reference = screen.getByRole('region', { name: '参考数据' })
    expect(within(reference).getByRole('heading', { name: 'Trading calendar' })).toBeInTheDocument()
  })

  it('renders fixed ext pools and remainder under the extension group', () => {
    render(<DataCatalogSection catalog={catalogFixture} />)
    const ext = screen.getByRole('region', { name: '扩展数据' })
    expect(ext).toHaveAttribute('id', 'catalog-group-ext')
    expect(within(ext).getByRole('heading', { name: '行业资金流日线' })).toBeInTheDocument()
    expect(within(ext).getByRole('heading', { name: '扩展数据余项' })).toBeInTheDocument()
  })

  it('renders margin trading as a separate stock F10 business', () => {
    render(<DataCatalogSection catalog={catalogFixture} />)

    const f10 = screen.getByRole('region', { name: '股票 F10' })
    expect(within(f10).getByRole('heading', { name: '个股融资融券' })).toBeInTheDocument()
    expect(within(f10).getByText('1')).toBeInTheDocument()
  })

  it('renders first-class quote, sealed-L1, and pool cards and selects by accessible control', () => {
    const onSelect = vi.fn()
    render(<DataCatalogSection catalog={catalogFixture} onSelectDataset={onSelect} />)

    for (const title of ['Quote snapshots', '封板 L1', 'Stock pools']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }
    fireEvent.click(screen.getByRole('button', { name: '查看 Stock pools 详情' }))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({
      descriptor: expect.objectContaining({ dataset_id: 'pools' }),
    }))
  })

  it('renders a complete dataset card with raw-byte local size and honest quality', () => {
    render(<DatasetCatalogCard entry={makeEntry('stock_daily', 'A 股日 K')} />)

    expect(screen.getByText('stock · symbol-date')).toBeInTheDocument()
    expect(screen.getByText('12,345')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('2024-01-02')).toBeInTheDocument()
    expect(screen.getByText('2026-07-20')).toBeInTheDocument()
    expect(screen.getByText('1.5 KiB')).toBeInTheDocument()
    expect(screen.getByText('降级')).toBeInTheDocument()
    expect(screen.queryByText('准入状态未登记')).not.toBeInTheDocument()
    expect(screen.queryByText('未使用控制库准入')).not.toBeInTheDocument()
    expect(screen.getByLabelText('数据源支持：是')).toBeInTheDocument()
    expect(screen.getByLabelText('当前有权限：否')).toBeInTheDocument()
  })

  it('orders market coverage as SH, SZ, BJ and keeps unknown denominators explicit', () => {
    render(<CoverageBar coverage={makeEntry('daily').coverage} />)

    const markets = screen.getAllByTestId('coverage-market').map((node) => node.textContent)
    expect(markets).toEqual(['SH', 'SZ', 'BJ'])
    expect(screen.getByText('60 / 75')).toBeInTheDocument()
    expect(screen.getByText('20 / 未知')).toBeInTheDocument()
  })

  it('keeps SH, SZ, and BJ visible when the backend has no market facts', () => {
    render(<CoverageBar coverage={[]} />)

    const markets = screen.getAllByTestId('coverage-market').map((node) => node.textContent)
    expect(markets).toEqual(['SH', 'SZ', 'BJ'])
    expect(screen.getAllByText('未知 / 未知')).toHaveLength(3)
  })

  it('shows a backend ratio visibly when the expected symbol denominator is unknown', () => {
    render(<CoverageBar coverage={[
      { market: 'SH', symbol_count: 27, expected_symbol_count: null, ratio: 0.375 },
    ]} />)

    const shRow = screen.getByText('SH').closest('div')
    expect(shRow).not.toBeNull()
    expect(within(shRow!).getByText('27 / 未知')).toBeInTheDocument()
    expect(within(shRow!).getByText('37.5%')).toBeInTheDocument()
  })

  it('renders inline initial error and empty states without throwing', () => {
    const { rerender } = render(<DataCatalogSection error={new Error('catalog unavailable')} />)
    expect(screen.getByRole('alert')).toHaveTextContent('catalog unavailable')

    rerender(<DataCatalogSection catalog={{ ...catalogFixture, datasets: [] }} />)
    expect(screen.getByText('暂无数据目录')).toBeInTheDocument()
  })

  it('keeps the admin offline-margin fold outside catalog groups and collapsed by default', () => {
    const meta = vi.spyOn(api, 'externalReadonlySources')
    render(<DataCatalogSection catalog={catalogFixture} isAdmin />)

    const fold = screen.getByRole('button', { name: /外部只读原包·两融查询/ })
    expect(fold).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('两融股票代码')).not.toBeInTheDocument()
    expect(meta).not.toHaveBeenCalled()
    expect(screen.queryByText(/80\s*GB|80GB/)).not.toBeInTheDocument()

    const f10 = screen.getByRole('region', { name: '股票 F10' })
    expect(within(f10).getByRole('heading', { name: '个股融资融券' })).toBeInTheDocument()
    expect(within(f10).getByText('1')).toBeInTheDocument()
    expect(within(f10).queryByText(/外部只读原包/)).not.toBeInTheDocument()
  })

  it('mounts the offline query only after an admin expands the fold', async () => {
    const meta = vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
      root_path: '/tmp/fixture-quantdb',
    })
    const query = vi.spyOn(api, 'getMarginTrading')
    renderCatalog(<DataCatalogSection catalog={catalogFixture} isAdmin />)

    expect(meta).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /外部只读原包·两融查询/ }))
    expect(await screen.findByLabelText('两融股票代码')).toBeInTheDocument()
    await waitFor(() => expect(meta).toHaveBeenCalledTimes(1))
    expect(query).not.toHaveBeenCalled()
    expect(screen.getByText('截止按标的查询获取。')).toBeInTheDocument()
    expect(document.getElementById('catalog-offline-margin-symbol')).toBeInTheDocument()
  })

  it('does not render the offline-margin fold or request metadata for ordinary users', () => {
    const meta = vi.spyOn(api, 'externalReadonlySources')
    render(<DataCatalogSection catalog={catalogFixture} isAdmin={false} />)

    expect(screen.queryByRole('button', { name: /外部只读原包·两融查询/ })).not.toBeInTheDocument()
    expect(meta).not.toHaveBeenCalled()
  })
})
