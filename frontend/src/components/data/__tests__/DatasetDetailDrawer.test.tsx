import { fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { DatasetDetailDrawer } from '../DatasetDetailDrawer'
import { DatasetRunHistory } from '../DatasetRunHistory'
import { QualityLineagePanel } from '../QualityLineagePanel'
import { failedRun, makeEntry } from './catalogFixtures'

function DrawerHarness() {
  const [entry, setEntry] = useState<ReturnType<typeof makeEntry> | null>(null)

  return <>
    <button type="button" onClick={() => setEntry(makeEntry('stock_daily', 'A 股日 K'))}>打开数据详情</button>
    <DatasetDetailDrawer entry={entry} onClose={() => setEntry(null)} />
  </>
}

describe('dataset details', () => {
  it('shows field unit, scale, currency, timezone and descriptor metadata', () => {
    render(<DatasetDetailDrawer entry={makeEntry('stock_daily', 'A 股日 K')} runs={[failedRun]} onClose={() => {}} />)

    const dialog = screen.getByRole('dialog', { name: 'A 股日 K 详情' })
    expect(within(dialog).queryByText('close')).not.toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: '高级信息' }))
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

    fireEvent.click(screen.getByRole('button', { name: '高级信息' }))
    expect(screen.getByText('amount')).toBeInTheDocument()
    expect(screen.queryByText('close')).not.toBeInTheDocument()
    expect(screen.getByText('未声明')).toBeInTheDocument()
  })

  it('moves focus inside on open and wraps focus across progressive disclosure', () => {
    render(<DrawerHarness />)
    const trigger = screen.getByRole('button', { name: '打开数据详情' })
    trigger.focus()

    fireEvent.click(trigger)

    const close = screen.getByRole('button', { name: /关闭.*A 股日 K.*详情/ })
    const advanced = screen.getByRole('button', { name: '高级信息' })
    expect(close).toHaveFocus()
    advanced.focus()
    fireEvent.keyDown(advanced, { key: 'Tab' })
    expect(close).toHaveFocus()
    close.focus()
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
    expect(advanced).toHaveFocus()
  })

  it('wraps Tab and Shift+Tab across future drawer focusables', () => {
    render(<DatasetDetailDrawer entry={makeEntry('daily', '日 K')} onClose={() => {}} />)
    const dialog = screen.getByRole('dialog', { name: '日 K 详情' })
    const close = screen.getByRole('button', { name: /关闭.*日 K.*详情/ })
    const futureAction = document.createElement('button')
    futureAction.textContent = '未来操作'
    dialog.append(futureAction)

    futureAction.focus()
    fireEvent.keyDown(futureAction, { key: 'Tab' })
    expect(close).toHaveFocus()

    close.focus()
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('button', { name: '未来操作' })).toHaveFocus()
  })

  it('returns focus to the trigger after the drawer closes', () => {
    render(<DrawerHarness />)
    const trigger = screen.getByRole('button', { name: '打开数据详情' })
    trigger.focus()
    fireEvent.click(trigger)

    const close = screen.getByRole('button', { name: /关闭.*A 股日 K.*详情/ })
    close.focus()
    fireEvent.click(close)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('closes through its naturally named button and Escape', () => {
    const onClose = vi.fn()
    const { rerender } = render(<DatasetDetailDrawer entry={makeEntry('daily', '日 K')} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: '关闭“日 K”详情' }))
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
    fireEvent.click(screen.getByRole('button', { name: '高级信息' }))

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

  it('uses unique semantic heading ids for multiple lineage and run panels', () => {
    render(<>
      <QualityLineagePanel entry={makeEntry('first')} />
      <QualityLineagePanel entry={makeEntry('second')} />
      <DatasetRunHistory runs={[]} />
      <DatasetRunHistory runs={[]} />
    </>)

    const lineageHeadingIds = screen.getAllByRole('heading', { name: '质量与血缘' }).map((heading) => heading.id)
    const runHeadingIds = screen.getAllByRole('heading', { name: '最近运行' }).map((heading) => heading.id)
    expect(new Set(lineageHeadingIds).size).toBe(2)
    expect(new Set(runHeadingIds).size).toBe(2)
  })
})
