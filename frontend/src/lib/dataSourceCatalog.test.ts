import { describe, expect, it } from 'vitest'
import { makeEntry } from '@/components/data/__tests__/catalogFixtures'
import type {
  CapabilityMatrix,
  CapabilityRoute,
  CatalogResponse,
  DataSourcesResponse,
  SourceProvenanceResponse,
} from './api'
import {
  EXTERNAL_SOURCE_ID,
  UNREGISTERED_SOURCE_ID,
  buildUnifiedSources,
  canonicalProviderName,
  coverageTimeLabel,
  extraDatasetLabel,
  fieldUnitLabel,
  isLocallyPresent,
  producerNamesFor,
} from './dataSourceCatalog'

function cap(id: string, extras: Partial<CapabilityRoute> = {}): CapabilityRoute {
  return {
    id,
    label: id,
    desc: '',
    field: `${id}_data_provider` as CapabilityRoute['field'],
    default: 'tickflow',
    tf_tier: 'none',
    tf_available: true,
    usable: true,
    current: 'tickflow',
    current_display: 'TickFlow',
    effective: 'tickflow',
    effective_display: 'TickFlow',
    candidates: [
      { name: 'tickflow', display: 'TickFlow', kind: 'builtin', available: true, status: 'ok' },
      { name: 'public', display: '公开源', kind: 'builtin', available: true, status: 'ok' },
    ],
    pending: [],
    ...extras,
  }
}

const sources: DataSourcesResponse = {
  builtin: [{ name: 'tickflow', display_name: 'TickFlow', datasets: ['daily', 'adj_factor'] }],
  plugins: [{
    name: 'hithink',
    display_name: '同花顺',
    datasets: ['minute'],
    runtime: 'python',
    available: true,
    status: 'ok',
    description: '',
    install_hint: '',
  }, {
    name: 'fuyao',
    display_name: '扶摇',
    datasets: ['financial'],
    runtime: 'python',
    available: true,
    status: 'ok',
    description: '',
    install_hint: '',
  }],
  custom: [{ name: 'my_http', display_name: '自建源', datasets: ['daily'] }],
  errors: [],
  config_dir: '/tmp',
}

const matrix: CapabilityMatrix = {
  tickflow_tier: 'none',
  capabilities: [
    cap('daily', {
      current: 'tickflow',
      current_display: 'TickFlow',
      effective: 'tickflow',
      effective_display: 'TickFlow',
    }),
    cap('financial', {
      current: 'public',
      current_display: '公开源',
      effective: 'public',
      effective_display: '公开源',
    }),
  ],
}

const catalog: CatalogResponse = {
  datasets: [
    makeEntry('stock_daily', 'Stock daily bars', { provider: 'local_public' }),
    makeEntry('financial_metrics', 'Financial metrics', { provider: 'local_public' }),
    makeEntry('stock_margin_trading', '个股融资融券', { provider: 'local_public' }),
    makeEntry('mystery_bars', 'Mystery bars', {
      provider: null,
      lineage: [{
        run_id: 'run-x',
        source: 'public_feed',
        fetched_at: null,
        unit_version: 'v1',
        quality_status: 'unknown',
        scope: null,
        artifact_path: null,
        row_count: null,
      }],
    }),
    makeEntry('custom_only', 'Custom only', { provider: 'shop_floor' }),
    makeEntry('empty_descriptor', 'Empty descriptor', {
      provider: 'tickflow',
      descriptor: {
        ...makeEntry('empty_descriptor').descriptor,
        dataset_id: 'empty_descriptor',
        availability: {
          provider_supported: true,
          entitled: true,
          local_materialized: false,
          serving_ready: false,
          reason_code: null,
        },
        fields: [],
      },
      state: {
        ...makeEntry('empty_descriptor').state,
        dataset_id: 'empty_descriptor',
        row_count: 0,
        earliest_time: null,
        latest_time: null,
      },
    }),
  ],
  storage: { managed_data_bytes: 0, operational_bytes: 0, total_bytes: 0, categories: [] },
  refreshed_at: null,
  stale: false,
}

const provenance = {
  records: [{
    subject_id: 'stock_daily',
    true_producers: [{
      producer_id: 'public_quote',
      name: '腾讯 / 新浪公开行情端点',
      kind: 'public_web_endpoint',
      role: 'quote_and_eod_fallback',
    }],
    local_chain: { providers: ['public', 'public_feed'], lineage_sources: ['public_feed'], materialized: true, serving_ready: true },
  }],
} as SourceProvenanceResponse

describe('canonicalProviderName', () => {
  it('aliases local_public to public and drops routing aliases', () => {
    expect(canonicalProviderName('local_public')).toBe('public')
    expect(canonicalProviderName('public')).toBe('public')
    expect(canonicalProviderName('same_as_daily')).toBeNull()
    expect(canonicalProviderName(null)).toBeNull()
  })
})

describe('buildUnifiedSources', () => {
  it('lists every API source, not only TickFlow/fuyao/stock-sdk', () => {
    const cards = buildUnifiedSources({ sources, matrix, catalog })
    expect(cards.map((item) => item.name)).toEqual(
      expect.arrayContaining(['tickflow', 'hithink', 'fuyao', 'my_http', 'public']),
    )
    expect(cards.some((item) => item.id === 'stock-sdk')).toBe(false)
  })

  it('groups local_public datasets onto 公开源 and does not use current TickFlow routing', () => {
    const cards = buildUnifiedSources({ sources, matrix, catalog })
    const pub = cards.find((item) => item.name === 'public')
    const tickflow = cards.find((item) => item.name === 'tickflow')
    expect(pub?.datasetIds).toEqual(expect.arrayContaining(['stock_daily', 'financial_metrics', 'stock_margin_trading']))
    expect(tickflow?.datasetIds).toEqual(['empty_descriptor'])
    expect(pub?.extraLabels).toContain('两融')
    expect(pub?.paid).toBe(false)
    expect(tickflow?.paid).toBe(true)
    expect(tickflow?.tier).toBe('none')
    expect(pub?.capabilityIds).not.toContain('full_minute')
  })

  it('keeps unknown HTTP providers as local cards and unknown evidence as 未登记', () => {
    const cards = buildUnifiedSources({ sources, matrix, catalog })
    const local = cards.find((item) => item.kind === 'local')
    const unknown = cards.find((item) => item.kind === 'unregistered')
    expect(local?.name).toBe('shop_floor')
    expect(local?.datasetIds).toEqual(['custom_only'])
    expect(unknown?.id).toBe(UNREGISTERED_SOURCE_ID)
    expect(unknown?.datasetIds).toEqual(['mystery_bars'])
    expect(cards.find((item) => item.name === 'public')?.datasetIds).not.toContain('mystery_bars')
  })

  it('does not invent an external writable route and only adds the read-only card when asked', () => {
    expect(buildUnifiedSources({ sources, matrix, catalog }).some((item) => item.kind === 'external')).toBe(false)
    const withExternal = buildUnifiedSources({ sources, matrix, catalog, includeExternal: true })
    const external = withExternal.find((item) => item.id === EXTERNAL_SOURCE_ID)
    expect(external?.kind).toBe('external')
    expect(external?.datasetIds).toEqual([])
    expect(external?.extraLabels).toEqual(['两融'])
    expect(external?.capabilityIds).toEqual([])
  })
})

describe('evidence labels', () => {
  it('uses 未知/未登记 instead of zeros and does not treat descriptors as landed files', () => {
    const empty = catalog.datasets.find((item) => item.descriptor.dataset_id === 'empty_descriptor')!
    expect(coverageTimeLabel(empty)).toBe('未知')
    expect(isLocallyPresent(empty)).toBe(false)
    expect(fieldUnitLabel(null)).toBe('未登记')
    expect(extraDatasetLabel('stock_margin_trading')).toBe('两融')
    expect(producerNamesFor('stock_daily', provenance)).toEqual(['腾讯 / 新浪公开行情端点'])
    expect(producerNamesFor('mystery_bars', provenance)).toEqual(['未登记'])
  })
})
