import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { ExternalReadOnlyData } from '../ExternalReadOnlyData'

async function submitSymbol(value: string) {
  fireEvent.change(screen.getByLabelText('两融股票代码'), { target: { value } })
  const button = await screen.findByRole('button', { name: /查询两融/ })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
}

function renderBlock(isAdmin = true, extra?: { compact?: boolean; idPrefix?: string }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <ExternalReadOnlyData isAdmin={isAdmin} compact={extra?.compact} idPrefix={extra?.idPrefix} />
      </QueryClientProvider>,
    ),
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ExternalReadOnlyData', () => {
  it('shows unconfigured and does not query or write back', async () => {
    const meta = vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'unconfigured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: '外置只读包目前仅支持按标的查询两融，不是全包已入库，也不计入托管存储。',
      root_path: null,
    })
    const query = vi.spyOn(api, 'getMarginTrading')
    const sync = vi.spyOn(api, 'syncMarginTrading')
    renderBlock()

    expect(await screen.findByText('未配置')).toBeInTheDocument()
    expect(screen.getByText(/目前支持：两融/)).toBeInTheDocument()
    expect(screen.getByText('截止按标的查询获取。')).toBeInTheDocument()
    expect(screen.queryByText(/80/)).not.toBeInTheDocument()
    expect(screen.queryByText('2026-08-26')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查询两融' })).toBeDisabled()
    fireEvent.submit(screen.getByRole('button', { name: '查询两融' }).closest('form')!)
    expect(query).not.toHaveBeenCalled()
    expect(sync).not.toHaveBeenCalled()
    expect(meta).toHaveBeenCalledTimes(1)
  })

  it('does not request admin metadata or expose a path when isAdmin is false', async () => {
    const meta = vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'inaccessible',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
      root_path: '/tmp/fixture-quantdb',
    })
    renderBlock(false)
    expect(screen.queryByText('/tmp/fixture-quantdb')).not.toBeInTheDocument()
    expect(screen.queryByText('配置路径（管理员）')).not.toBeInTheDocument()
    await waitFor(() => expect(meta).not.toHaveBeenCalled())
  })

  it('lets admin expand the configured path and query a sample', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
      root_path: '/tmp/fixture-quantdb',
    })
    const query = vi.spyOn(api, 'getMarginTrading').mockResolvedValue({
      data: [{
        symbol: '000001.SZ',
        trade_date: '2026-08-04',
        financing_balance: 100,
        securities_lending_balance: null,
        securities_lending_balance_volume: 12,
        source: 'offline_quantdb',
      }],
      count: 1,
      source: 'offline_quantdb',
      as_of: '2026-08-04',
      status: 'ok',
      missing_fields: ['securities_lending_balance'],
    })
    renderBlock(true)

    expect(await screen.findByText('已配置')).toBeInTheDocument()
    expect(screen.getByText(/已配置不代表全部数据可读/)).toBeInTheDocument()
    expect(screen.getByText('截止按标的查询获取。')).toBeInTheDocument()
    fireEvent.click(screen.getByText('配置路径（管理员）'))
    expect(screen.getByText('/tmp/fixture-quantdb')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('两融股票代码'), { target: { value: '000001.SZ' } })
    expect(query).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '查询两融' }))

    await waitFor(() => expect(query).toHaveBeenCalledWith({
      symbol: '000001.SZ',
      source: 'offline_quantdb',
      limit: 20,
    }))
    expect(await screen.findByText(/来源 offline_quantdb · 截止日 2026-08-04 · 最多 20 条/)).toBeInTheDocument()
    expect(screen.getByText('缺字段：securities_lending_balance')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(screen.queryByText('截止按标的查询获取。')).not.toBeInTheDocument()
  })

  it('shows a missing-file error for a bad symbol', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    const query = vi.spyOn(api, 'getMarginTrading').mockRejectedValue(
      new Error('offline margin file not found for BAD.SZ'),
    )
    renderBlock(true)
    await screen.findByText('已配置')
    await submitSymbol('BAD.SZ')
    expect(await screen.findByText(/没有该标的的两融文件/)).toBeInTheDocument()
    expect(query).toHaveBeenCalledWith({ symbol: 'BAD.SZ', source: 'offline_quantdb', limit: 20 })
  })

  it('shows a true empty record separately from read errors', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    vi.spyOn(api, 'getMarginTrading').mockResolvedValue({
      data: [],
      count: 0,
      source: 'offline_quantdb',
      as_of: '2026-08-04',
      status: 'empty',
    })
    renderBlock(true)
    await screen.findByText('已配置')
    await submitSymbol('000001.SZ')
    expect(await screen.findByText(/当前条件没有记录 · 来源 offline_quantdb · 截止日 2026-08-04/)).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '融资余额' })).not.toBeInTheDocument()
  })

  it('shows an unreadable file as a read error, not an empty success', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    vi.spyOn(api, 'getMarginTrading').mockRejectedValue(
      new Error('offline margin file unreadable for 000001.SZ'),
    )
    renderBlock(true)
    await screen.findByText('已配置')
    await submitSymbol('000001.SZ')
    expect(await screen.findByText(/两融文件无法读取/)).toBeInTheDocument()
    expect(screen.queryByText(/当前条件没有记录/)).not.toBeInTheDocument()
  })

  it('does not send a path argument to the metadata API', async () => {
    const meta = vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    renderBlock(true)
    await screen.findByText('已配置')
    expect(meta).toHaveBeenCalled()
    expect(JSON.stringify(meta.mock.calls)).not.toContain('/etc')
  })

  it('refetches the same symbol after a failed query', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    const query = vi.spyOn(api, 'getMarginTrading')
      .mockRejectedValueOnce(new Error('offline margin file unreadable for 000001.SZ'))
      .mockResolvedValueOnce({
        data: [{
          symbol: '000001.SZ',
          trade_date: '2026-08-04',
          financing_balance: 100,
          securities_lending_balance: null,
          securities_lending_balance_volume: 12,
          source: 'offline_quantdb',
        }],
        count: 1,
        source: 'offline_quantdb',
        as_of: '2026-08-04',
        status: 'ok',
      })
    renderBlock(true)
    await screen.findByText('已配置')
    await submitSymbol('000001.SZ')
    expect(await screen.findByText(/两融文件无法读取/)).toBeInTheDocument()
    expect(screen.queryByText('100')).not.toBeInTheDocument()
    await submitSymbol('000001.SZ')
    await waitFor(() => expect(query).toHaveBeenCalledTimes(2))
    expect(query).toHaveBeenNthCalledWith(2, { symbol: '000001.SZ', source: 'offline_quantdb', limit: 20 })
    expect(await screen.findByText('100')).toBeInTheDocument()
    expect(screen.queryByText(/两融文件无法读取/)).not.toBeInTheDocument()
  })

  it('does not keep a previous success table after a later error', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    const query = vi.spyOn(api, 'getMarginTrading')
      .mockResolvedValueOnce({
        data: [{
          symbol: '000001.SZ',
          trade_date: '2026-08-04',
          financing_balance: 100,
          securities_lending_balance: null,
          securities_lending_balance_volume: 12,
          source: 'offline_quantdb',
        }],
        count: 1,
        source: 'offline_quantdb',
        as_of: '2026-08-04',
        status: 'ok',
      })
      .mockRejectedValueOnce(new Error('offline margin file not found for BAD.SZ'))
    renderBlock(true)
    await screen.findByText('已配置')
    await submitSymbol('000001.SZ')
    expect(await screen.findByText('100')).toBeInTheDocument()
    await submitSymbol('BAD.SZ')
    expect(await screen.findByText(/没有该标的的两融文件/)).toBeInTheDocument()
    expect(screen.queryByText('100')).not.toBeInTheDocument()
    expect(screen.queryByText(/截止日 2026-08-04/)).not.toBeInTheDocument()
    expect(query).toHaveBeenLastCalledWith({ symbol: 'BAD.SZ', source: 'offline_quantdb', limit: 20 })
  })

  it('does not keep the previous symbol after switching to another success', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    vi.spyOn(api, 'getMarginTrading')
      .mockResolvedValueOnce({
        data: [{
          symbol: '000001.SZ',
          trade_date: '2026-08-04',
          financing_balance: 100,
          securities_lending_balance: null,
          securities_lending_balance_volume: 12,
          source: 'offline_quantdb',
        }],
        count: 1,
        source: 'offline_quantdb',
        as_of: '2026-08-04',
        status: 'ok',
      })
      .mockResolvedValueOnce({
        data: [{
          symbol: '300502.SZ',
          trade_date: '2026-08-26',
          financing_balance: 250,
          securities_lending_balance: 8,
          securities_lending_balance_volume: 3,
          source: 'offline_quantdb',
        }],
        count: 1,
        source: 'offline_quantdb',
        as_of: '2026-08-26',
        status: 'ok',
      })
    renderBlock(true)
    await screen.findByText('已配置')
    await submitSymbol('000001.SZ')
    expect(await screen.findByText('100')).toBeInTheDocument()
    await submitSymbol('300502.SZ')
    expect(await screen.findByText(/截止日 2026-08-26/)).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
    expect(screen.queryByText('100')).not.toBeInTheDocument()
    expect(screen.queryByText('2026-08-04')).not.toBeInTheDocument()
  })

  it('hides a successful result as soon as the draft symbol diverges and never shows it while the next query is pending', async () => {
    type MarginResult = Awaited<ReturnType<typeof api.getMarginTrading>>
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    let resolveB!: (value: MarginResult) => void
    const query = vi.spyOn(api, 'getMarginTrading')
      .mockResolvedValueOnce({
        data: [{
          symbol: '300502.SZ',
          trade_date: '2026-08-26',
          financing_balance: 250,
          securities_lending_balance: 8,
          securities_lending_balance_volume: 3,
          source: 'offline_quantdb',
        }],
        count: 1,
        source: 'offline_quantdb',
        as_of: '2026-08-26',
        status: 'ok',
      })
      .mockImplementationOnce(() => new Promise<MarginResult>((resolve) => {
        resolveB = resolve
      }))
    renderBlock(true)
    await screen.findByText('已配置')
    await submitSymbol('300502.SZ')
    expect(await screen.findByText('250')).toBeInTheDocument()
    expect(screen.getByText(/截止日 2026-08-26/)).toBeInTheDocument()
    expect(query).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('两融股票代码'), { target: { value: '000000.SZ' } })
    expect(screen.queryByText('250')).not.toBeInTheDocument()
    expect(screen.queryByText(/截止日 2026-08-26/)).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '融资余额' })).not.toBeInTheDocument()
    expect(query).toHaveBeenCalledTimes(1)

    const button = await screen.findByRole('button', { name: /查询两融/ })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    expect(await screen.findByText('正在查询两融')).toBeInTheDocument()
    expect(screen.queryByText('250')).not.toBeInTheDocument()
    expect(screen.queryByText(/截止日 2026-08-26/)).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '融资余额' })).not.toBeInTheDocument()

    resolveB({
      data: [{
        symbol: '000000.SZ',
        trade_date: '2026-09-01',
        financing_balance: 80,
        securities_lending_balance: 1,
        securities_lending_balance_volume: 2,
        source: 'offline_quantdb',
      }],
      count: 1,
      source: 'offline_quantdb',
      as_of: '2026-09-01',
      status: 'ok',
    })
    expect(await screen.findByText('80')).toBeInTheDocument()
    expect(screen.getByText(/截止日 2026-09-01/)).toBeInTheDocument()
    expect(screen.queryByText('250')).not.toBeInTheDocument()
    expect(screen.queryByText('2026-08-26')).not.toBeInTheDocument()
    await waitFor(() => expect(query).toHaveBeenCalledTimes(2))
    expect(query).toHaveBeenLastCalledWith({ symbol: '000000.SZ', source: 'offline_quantdb', limit: 20 })
  })

  it('uses a distinct input id in compact nested mode', async () => {
    vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
      status: 'configured',
      supported: [{ id: 'margin_trading', label: '两融' }],
      note: 'x',
    })
    renderBlock(true, { compact: true, idPrefix: 'catalog-offline-margin' })
    expect(await screen.findByText('已配置')).toBeInTheDocument()
    expect(document.getElementById('catalog-offline-margin-symbol')).toBeInTheDocument()
    expect(document.getElementById('offline-margin-symbol')).not.toBeInTheDocument()
  })
})
