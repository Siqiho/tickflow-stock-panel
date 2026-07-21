import type {
  CatalogResponse,
  DatasetCatalogEntry,
  StorageBreakdown,
  SyncRun,
} from '@/lib/api'

export function makeEntry(
  datasetId: string,
  title = datasetId,
  overrides: Partial<DatasetCatalogEntry> = {},
): DatasetCatalogEntry {
  return {
    descriptor: {
      dataset_id: datasetId,
      title,
      asset_types: ['stock'],
      grain: 'symbol-date',
      primary_key: ['symbol', 'date'],
      partition_keys: ['date'],
      schema_version: 'v1',
      unit_version: 'cn_market_v1',
      point_in_time: true,
      adjustment: 'none',
      availability: {
        provider_supported: true,
        entitled: false,
        local_materialized: true,
        serving_ready: false,
        reason_code: 'entitlement_required',
      },
      fields: [{
        name: 'close',
        dtype: 'float64',
        semantic: '收盘价',
        unit: '元',
        scale: '0.01',
        currency: 'CNY',
        timezone: 'Asia/Shanghai',
        nullable: false,
      }],
    },
    state: {
      dataset_id: datasetId,
      schema_version: 'v1',
      unit_version: 'cn_market_v1',
      quality_status: 'degraded',
      row_count: 12_345,
      symbol_count: 120,
      expected_symbol_count: 150,
      earliest_time: '2024-01-02',
      latest_time: '2026-07-20',
      managed_bytes: 1_536,
      last_run_id: 'run-1',
      updated_at: '2026-07-21T08:30:00Z',
      payload: {},
    },
    provider: 'local_public',
    coverage: [
      { market: 'BJ', symbol_count: 20, expected_symbol_count: null, ratio: null },
      { market: 'SH', symbol_count: 60, expected_symbol_count: 75, ratio: 0.8 },
      { market: 'SZ', symbol_count: 40, expected_symbol_count: 50, ratio: 0.8 },
    ],
    lineage: [{
      run_id: 'run-1',
      source: 'public_feed',
      fetched_at: '2026-07-21T08:00:00Z',
      unit_version: 'cn_market_v1',
      quality_status: 'degraded',
      scope: 'SH,SZ,BJ',
      artifact_path: 'stocks/daily/date=2026-07-20/part.parquet',
      row_count: 12_345,
    }],
    depth5_available: false,
    ...overrides,
  }
}

export const financeEntries = [
  makeEntry('financial_metrics', 'Financial metrics'),
  makeEntry('financial_income', 'Income statements'),
  makeEntry('financial_balance_sheet', 'Balance sheets'),
  makeEntry('financial_cash_flow', 'Cash-flow statements'),
  makeEntry('financial_shares', 'Shares outstanding'),
]

export const storageFixture: StorageBreakdown = {
  managed_data_bytes: 1_000,
  operational_bytes: 200,
  total_bytes: 9_999,
  categories: [
    { key: 'daily', title: '日线', kind: 'managed', bytes: 50, files: 2 },
    { key: 'control', title: '控制库', kind: 'operational', bytes: 25, files: 1 },
  ],
}

export const catalogFixture: CatalogResponse = {
  datasets: [
    makeEntry('stock_daily', 'Stock daily bars'),
    makeEntry('etf_daily', 'ETF daily bars'),
    makeEntry('quote_snapshot', 'Quote snapshots'),
    makeEntry('sealed_l1', 'Sealed L1 quotes'),
    makeEntry('depth5', 'Five-level order book'),
    makeEntry('pools', 'Stock pools'),
    ...financeEntries,
  ],
  storage: storageFixture,
  refreshed_at: '2026-07-21T08:31:00Z',
  stale: false,
}

export const failedRun: SyncRun = {
  run_id: 'run-failed',
  dataset_id: 'stock_daily',
  provider: 'local_public',
  operation: 'scan',
  started_at: '2026-07-21T08:00:00Z',
  finished_at: '2026-07-21T08:02:00Z',
  status: 'failed',
  rows_fetched: 88,
  rows_published: 55,
  quality_status: 'failed',
  error_code: 'schema_mismatch',
  error_message: 'upstream field count changed and publication was stopped',
}
