import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { HithinkSpecialDataSyncCard } from '../HithinkSpecialDataSyncCard'
import { api } from '@/lib/api'

function renderCard(onTraceSource = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <HithinkSpecialDataSyncCard onTraceSource={onTraceSource} />
    </QueryClientProvider>,
  )
  return { client, onTraceSource }
}

afterEach(() => {
  vi.restoreAllMocks()
})

it('syncs the selected Shanghai date and reports independent published rows', async () => {
  const sync = vi.spyOn(api, 'syncHithinkSpecialData').mockResolvedValue({
    requested_date: '2026-08-25',
    resolved_date: '2026-08-25',
    rows_published: 18,
    datasets: [
      {
        dataset_id: 'hithink_limit_pool',
        rows_published: 12,
        artifact_path: 'reference/hithink_limit_pool/date=2026-08-25/part.parquet',
        lineage_path: 'lineage/hithink_limit_pool/date=2026-08-25/run.json',
        extra: {},
      },
      {
        dataset_id: 'hithink_auction_snapshot',
        rows_published: 2,
        artifact_path: 'reference/hithink_auction_snapshot/date=2026-08-25/part.parquet',
        lineage_path: 'lineage/hithink_auction_snapshot/date=2026-08-25/run.json',
        extra: { volume_unit: 'lot' },
      },
    ],
    catalog_refreshed: ['hithink_limit_pool', 'hithink_auction_snapshot'],
    source: 'hithink_fuyao',
  })
  renderCard()

  fireEvent.change(screen.getByLabelText('同花顺官方特色数据交易日期'), {
    target: { value: '2026-08-25' },
  })
  fireEvent.click(screen.getByRole('button', { name: '同步官方特色数据' }))

  await waitFor(() => {
    expect(sync).toHaveBeenCalledWith('2026-08-25')
  })
  expect(await screen.findByText(/已写入独立官方参考表 18 行/)).toBeInTheDocument()
  expect(screen.getByText(/hithink_limit_pool 12/)).toBeInTheDocument()
})

it('opens the official source trace instead of presenting GitHub as producer', () => {
  const { onTraceSource } = renderCard()

  fireEvent.click(screen.getByRole('button', { name: '查看同花顺官方特色数据来源' }))

  expect(onTraceSource).toHaveBeenCalledWith('hithink_limit_pool')
  expect(screen.getByText(/官方单源/)).toBeInTheDocument()
  expect(screen.getByText(/竞价量单位为手/)).toBeInTheDocument()
  expect(screen.getByText(/hithink_limit_pool/)).toBeInTheDocument()
  expect(screen.getByText(/参考数据/)).toBeInTheDocument()
})
