import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { StorageBreakdownCard } from '../StorageBreakdownCard'
import { storageFixture } from './catalogFixtures'

describe('StorageBreakdownCard', () => {
  it('uses backend totals directly even when category values are deliberately inconsistent', () => {
    render(<StorageBreakdownCard storage={storageFixture} refreshedAt="2026-07-21T08:31:00Z" />)

    expect(screen.getByTestId('managed-storage')).toHaveTextContent('1000 B')
    expect(screen.getByTestId('operational-storage')).toHaveTextContent('200 B')
    expect(screen.getByTestId('total-storage')).toHaveTextContent('9.8 KiB')
    expect(screen.getByTestId('total-storage')).not.toHaveTextContent('75 B')
    expect(screen.getByText('2026-07-21T08:31:00Z')).toBeInTheDocument()
  })

  it('marks stale storage explicitly', () => {
    render(<StorageBreakdownCard storage={storageFixture} isStale />)
    expect(screen.getByText('状态可能过期')).toBeInTheDocument()
  })

  it('renames storage buckets in Chinese and keeps ext_data as a directory bucket', () => {
    const onTraceSource = vi.fn()
    const onOpenCatalogGroup = vi.fn()
    render(
      <StorageBreakdownCard
        storage={{
          managed_data_bytes: 100,
          operational_bytes: 20,
          total_bytes: 120,
          categories: [
            { key: 'stocks', title: 'Stocks', kind: 'managed', bytes: 80, files: 10 },
            { key: 'ext_data', title: 'External data', kind: 'managed', bytes: 10, files: 396 },
            { key: 'reference', title: 'Reference data', kind: 'managed', bytes: 5, files: 4 },
            { key: 'quote_snapshot', title: 'Quote snapshot', kind: 'managed', bytes: 5, files: 2 },
          ],
        }}
        onTraceSource={onTraceSource}
        onOpenCatalogGroup={onOpenCatalogGroup}
      />,
    )

    expect(screen.getByText('股票')).toBeInTheDocument()
    expect(screen.getByText('扩展数据')).toBeInTheDocument()
    expect(screen.getByText('参考数据')).toBeInTheDocument()
    expect(screen.getByText('行情快照')).toBeInTheDocument()
    expect(screen.queryByText('External data')).not.toBeInTheDocument()
    expect(screen.queryByText('Stocks')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '追踪 股票 来源' }))
    expect(onTraceSource).toHaveBeenCalledWith('stock_daily')
    fireEvent.click(screen.getByRole('button', { name: '打开 扩展数据 目录' }))
    expect(onOpenCatalogGroup).toHaveBeenCalledWith('ext')
    fireEvent.click(screen.getByRole('button', { name: '打开 参考数据 目录' }))
    expect(onOpenCatalogGroup).toHaveBeenCalledWith('reference')
    fireEvent.click(screen.getByRole('button', { name: '追踪 行情快照 来源' }))
    expect(onTraceSource).toHaveBeenCalledWith('quote_snapshot')
  })
})
