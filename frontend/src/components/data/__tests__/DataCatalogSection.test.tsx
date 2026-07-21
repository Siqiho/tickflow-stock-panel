import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CoverageBar } from '../CoverageBar'
import { DataCatalogSection } from '../DataCatalogSection'
import { DatasetCatalogCard } from '../DatasetCatalogCard'
import { catalogFixture, makeEntry } from './catalogFixtures'

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
})
