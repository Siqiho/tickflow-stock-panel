import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { Indices } from '../Indices'

const unrelatedCatalogKeys = [
  QK.dataCatalogDataset('etf_daily'),
  QK.dataCatalogSchema('etf_daily'),
  QK.dataCatalogRuns('etf_daily'),
]

function catalogKeys(datasetIds: readonly string[]) {
  return [
    QK.dataStatus,
    QK.dataCatalog,
    QK.dataCatalogRuns(),
    ...datasetIds.flatMap((datasetId) => [
      QK.dataCatalogDataset(datasetId),
      QK.dataCatalogSchema(datasetId),
      QK.dataCatalogRuns(datasetId),
    ]),
  ]
}

function createClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  client.setQueryData(QK.capabilities, { capabilities: {}, features: {} })
  return client
}

function seedCatalogQueries(client: QueryClient, affectedKeys: readonly (readonly unknown[])[]) {
  for (const queryKey of [...affectedKeys, ...unrelatedCatalogKeys]) {
    client.setQueryData(queryKey, { cached: true })
  }
}

function expectInvalidationScope(
  client: QueryClient,
  affectedKeys: readonly (readonly unknown[])[],
) {
  for (const queryKey of affectedKeys) {
    expect(client.getQueryState(queryKey)?.isInvalidated).toBe(true)
  }
  for (const queryKey of unrelatedCatalogKeys) {
    expect(client.getQueryState(queryKey)?.isInvalidated).toBe(false)
  }
}

function renderIndices(client: QueryClient) {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Indices />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.spyOn(api, 'indexList').mockResolvedValue({ results: [], count: 0 })
  vi.spyOn(api, 'indexQuotes').mockResolvedValue({ rows: [], count: 0, source: 'none' })
  vi.spyOn(api, 'indexDaily').mockResolvedValue({ symbol: '000001.SH', rows: [], source: 'none' })
  vi.spyOn(api, 'syncIndexInstruments').mockResolvedValue({ status: 'ok', count: 2 })
  vi.spyOn(api, 'syncIndexDaily').mockResolvedValue({ status: 'ok', index_count: 2, rows_written: 20 })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Indices catalog invalidation', () => {
  it('invalidates only instrument catalog entries after syncing the index list', async () => {
    const client = createClient()
    const affectedKeys = catalogKeys(['index_instruments', 'etf_instruments'])
    seedCatalogQueries(client, affectedKeys)
    renderIndices(client)

    fireEvent.click(await screen.findByRole('button', { name: '同步指数列表' }))

    await waitFor(() => expect(api.syncIndexInstruments).toHaveBeenCalledTimes(1))
    await waitFor(() => expectInvalidationScope(client, affectedKeys))
  })

  it('invalidates only all actually written index catalog entries after syncing daily data', async () => {
    const client = createClient()
    const affectedKeys = catalogKeys([
      'index_instruments',
      'etf_instruments',
      'index_daily',
      'index_enriched',
    ])
    seedCatalogQueries(client, affectedKeys)
    renderIndices(client)

    fireEvent.click(await screen.findByRole('button', { name: '同步指数日K' }))

    await waitFor(() => expect(api.syncIndexDaily).toHaveBeenCalledWith(365))
    await waitFor(() => expectInvalidationScope(client, affectedKeys))
  })
})
