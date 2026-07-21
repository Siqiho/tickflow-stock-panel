import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DatasetDetailDrawer } from '../DatasetDetailDrawer'
import { DatasetRunHistory } from '../DatasetRunHistory'
import { QualityLineagePanel } from '../QualityLineagePanel'
import { failedRun, makeEntry } from './catalogFixtures'

describe('dataset details', () => {
  it('shows field unit, scale, currency, timezone and descriptor metadata', () => {
    render(<DatasetDetailDrawer entry={makeEntry('stock_daily', 'A 股日 K')} runs={[failedRun]} onClose={() => {}} />)

    const dialog = screen.getByRole('dialog', { name: 'A 股日 K 详情' })
    expect(within(dialog).getByText('close')).toBeInTheDocument()
    for (const value of ['float64', '收盘价', '元', '0.01', 'CNY', 'Asia/Shanghai']) {
      expect(within(dialog).getByText(value)).toBeInTheDocument()
    }
    expect(within(dialog).getByText('symbol, date')).toBeInTheDocument()
    expect(within(dialog).getByText('是')).toBeInTheDocument()
    expect(within(dialog).getAllByText('local_public').length).toBeGreaterThan(0)
    expect(within(dialog).getAllByText('entitlement_required').length).toBeGreaterThan(0)
  })

  it('uses supplied schema fields instead of descriptor fallback fields', () => {
    const entry = makeEntry('stock_daily', 'A 股日 K')
    render(<DatasetDetailDrawer
      entry={entry}
      schema={{
        dataset_id: 'stock_daily',
        schema_version: 'v2',
        unit_version: 'v2',
        fields: [{
          name: 'amount', dtype: 'int64', semantic: '成交额', unit: '元', scale: '1',
          currency: 'CNY', timezone: null, nullable: true,
        }],
      }}
      onClose={() => {}}
    />)

    expect(screen.getByText('amount')).toBeInTheDocument()
    expect(screen.queryByText('close')).not.toBeInTheDocument()
    expect(screen.getByText('未声明')).toBeInTheDocument()
  })

  it('closes through its named button and Escape', () => {
    const onClose = vi.fn()
    const { rerender } = render(<DatasetDetailDrawer entry={makeEntry('daily', '日 K')} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: '关闭日 K详情' }))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)

    rerender(<DatasetDetailDrawer entry={null} onClose={onClose} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders every lineage value and bounded run errors', () => {
    const entry = makeEntry('stock_daily', 'A 股日 K')
    render(<>
      <QualityLineagePanel entry={entry} />
      <DatasetRunHistory runs={[failedRun]} />
    </>)

    for (const value of [
      'public_feed', 'run-1', '2026-07-21T08:00:00Z', 'cn_market_v1',
      'SH,SZ,BJ', 'stocks/daily/date=2026-07-20/part.parquet', '12,345',
      'scan', 'run-failed', '88 / 55', 'schema_mismatch',
      'upstream field count changed and publication was stopped',
    ]) {
      expect(screen.getAllByText(value).length).toBeGreaterThan(0)
    }
    expect(screen.getAllByText('失败').length).toBeGreaterThan(0)
  })

  it('gives useful empty messages for lineage and runs', () => {
    render(<>
      <QualityLineagePanel entry={makeEntry('empty', 'Empty', { lineage: [] })} />
      <DatasetRunHistory runs={[]} />
    </>)
    expect(screen.getByText('暂无血缘记录')).toBeInTheDocument()
    expect(screen.getByText('暂无运行记录')).toBeInTheDocument()
  })
})
