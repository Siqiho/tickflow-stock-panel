import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { QK } from '../queryKeys'
import { useDataCatalog } from '../useSharedQueries'

const catalogResponse = {
  datasets: [{
    descriptor: {
      dataset_id: 'stock_daily',
      title: 'Stock daily',
      asset_types: ['stock'],
      grain: 'symbol-date',
      primary_key: ['symbol', 'date'],
      partition_keys: ['date'],
      schema_version: 'v1',
      unit_version: 'v1',
      point_in_time: true,
      adjustment: null,
      availability: {
        provider_supported: true,
        entitled: true,
        local_materialized: true,
        serving_ready: true,
        reason_code: null,
      },
      fields: [],
    },
    state: {
      dataset_id: 'stock_daily',
      schema_version: 'v1',
      unit_version: 'v1',
      quality_status: 'healthy',
      row_count: 1,
      symbol_count: 1,
      expected_symbol_count: 1,
      earliest_time: '2026-01-01',
      latest_time: '2026-01-01',
      managed_bytes: 1,
      last_run_id: 'run-1',
      updated_at: '2026-01-01T00:00:00Z',
      payload: {},
    },
    provider: 'local',
    coverage: [],
    lineage: [],
    depth5_available: false,
  }],
  storage: {
    managed_data_bytes: 1,
    operational_bytes: 0,
    total_bytes: 1,
    categories: [{ key: 'managed', title: 'Managed', kind: 'managed', bytes: 1, files: 1 }],
  },
  refreshed_at: '2026-01-01T00:00:00Z',
  stale: false,
}

function queryWrapper(client: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('data catalog client', () => {
  it('uses structurally distinct run keys for all runs and dataset id all', () => {
    expect(QK.dataCatalogRuns()).not.toEqual(QK.dataCatalogRuns('all'))
    expect(QK.dataCatalogRuns()).not.toEqual(QK.dataCatalogRuns('stock_daily'))
  })

  it('keeps the last catalog visible and marks it stale when a refetch fails', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(catalogResponse), { status: 200 }))
      .mockRejectedValueOnce(new TypeError('network unavailable'))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useDataCatalog({ refetchInterval: false }), {
      wrapper: queryWrapper(client),
    })

    await waitFor(() => expect(result.current.data).toEqual(catalogResponse))
    expect(result.current.isCatalogStale).toBe(false)

    await result.current.refetch()

    await waitFor(() => {
      expect(result.current.data).toEqual(catalogResponse)
      expect(result.current.isCatalogStale).toBe(true)
      expect(result.current.error).toBeInstanceOf(TypeError)
    })
  })

  it('uses encoded optional catalog parameters and no rescan body', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(
      new Response(JSON.stringify(catalogResponse), { status: 200 }),
    ))
    vi.stubGlobal('fetch', fetchMock)

    await api.rescanDataCatalog()
    await api.rescanDataCatalog('daily / stock')
    await api.dataCatalogRuns()
    await api.dataCatalogRuns('daily / stock')
    await api.dataControlSummary()

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/data/catalog/rescan',
      '/api/data/catalog/rescan?dataset_id=daily%20%2F%20stock',
      '/api/data/runs',
      '/api/data/runs?dataset_id=daily%20%2F%20stock',
      '/api/data/control-summary',
    ])
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' })
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'POST' })
    expect(fetchMock.mock.calls[1][1]?.body).toBeUndefined()
  })
})
