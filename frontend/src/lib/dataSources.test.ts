import { describe, expect, it } from 'vitest'
import {
  DATA_KEYS_SETTINGS_HREF,
  DATA_SOURCES_SETTINGS_HREF,
  capabilityStatusRows,
  catalogLocalDataLabel,
  classifyMarginQueryError,
  collectionHealthLabel,
  displaySourceName,
  findDataSource,
  formatMissingValue,
  marginQueryErrorLabel,
} from './dataSources'
import type { CapabilityMatrix, CatalogResponse, DataControlSummary, DataSourcesResponse } from './api'

const sources: DataSourcesResponse = {
  builtin: [{ name: 'tickflow', display_name: 'TickFlow', datasets: [] }],
  plugins: [{
    name: 'hithink',
    display_name: '同花顺',
    datasets: [],
    runtime: 'python',
    available: true,
    status: 'ok',
    description: '',
    install_hint: '',
  }],
  custom: [{ name: 'my_http', display_name: '自建源', datasets: [] }],
  errors: [],
  config_dir: '/tmp',
}

const emptyCatalog: CatalogResponse = {
  datasets: [],
  storage: { managed_data_bytes: 0, operational_bytes: 0, total_bytes: 0, categories: [] },
  refreshed_at: '2026-09-09T00:00:00Z',
  stale: false,
}

describe('unified data entry hrefs', () => {
  it('points the old settings data-sources tab at the single /data page', () => {
    expect(DATA_SOURCES_SETTINGS_HREF).toBe('/data?section=sources')
    expect(DATA_KEYS_SETTINGS_HREF).toBe('/settings?tab=account')
  })
})

describe('findDataSource', () => {
  it('resolves plugin and custom display names, not only custom', () => {
    expect(findDataSource(sources, 'hithink')?.display_name).toBe('同花顺')
    expect(findDataSource(sources, 'my_http')?.display_name).toBe('自建源')
    expect(findDataSource(sources, 'tickflow')?.display_name).toBe('TickFlow')
  })
})

describe('collectionHealthLabel', () => {
  it('does not treat zero consecutive failures as online', () => {
    const summary = {
      source_health: [
        { last_success_at: '2026-07-31T08:00:00Z', consecutive_failures: 0 },
        { last_success_at: '2026-07-31T08:00:00Z', consecutive_failures: 0 },
        { last_success_at: null, consecutive_failures: 2 },
      ],
    } as DataControlSummary
    const result = collectionHealthLabel(summary)
    expect(result.text).toContain('2 条有成功时间')
    expect(result.text).toContain('1 条连续失败')
    expect(result.text).not.toContain('正常')
    expect(result.unverified).toBe(false)
    expect(result.warning).toBe(true)
  })

  it('marks empty or success-less rows as unverified', () => {
    expect(collectionHealthLabel({ source_health: [] } as Pick<DataControlSummary, 'source_health'> as DataControlSummary).unverified).toBe(true)
    const noSuccess = collectionHealthLabel({
      source_health: [{ last_success_at: null, consecutive_failures: 0 }],
    } as DataControlSummary)
    expect(noSuccess.unverified).toBe(true)
    expect(noSuccess.text).toContain('采集健康未核验')
  })
})

describe('catalogLocalDataLabel', () => {
  it('separates loading, error, missing and local rows', () => {
    expect(catalogLocalDataLabel(undefined, ['stock_daily'], 'loading')).toBe('正在读取')
    expect(catalogLocalDataLabel(undefined, ['stock_daily'], 'error')).toBe('目录暂不可用')
    expect(catalogLocalDataLabel(emptyCatalog, ['stock_daily'], 'ready')).toBe('目录无记录')
    expect(catalogLocalDataLabel(emptyCatalog, undefined, 'ready')).toBe('目录无独立数据集')
  })
})

describe('capabilityStatusRows', () => {
  it('keeps configured source and readiness separate from local data', () => {
    const matrix: CapabilityMatrix = {
      tickflow_tier: 'none',
      capabilities: [{
        id: 'daily',
        label: '日K',
        desc: '',
        field: 'daily_data_provider',
        default: 'tickflow',
        tf_tier: 'none',
        tf_available: true,
        usable: true,
        current: 'tickflow',
        current_display: 'TickFlow',
        effective: 'tickflow',
        effective_display: 'TickFlow',
        candidates: [],
        pending: [],
      }, {
        id: 'realtime',
        label: '实时行情',
        desc: '',
        field: 'realtime_data_provider',
        default: 'tickflow',
        tf_tier: 'starter',
        tf_available: false,
        usable: false,
        current: 'tickflow',
        current_display: 'TickFlow',
        effective: 'tickflow',
        effective_display: 'TickFlow',
        candidates: [],
        pending: [],
      }],
    }
    const rows = capabilityStatusRows(matrix, emptyCatalog, 'ready')
    expect(rows[0].readyLabel).toBe('配置已就绪')
    expect(rows[0].localDataLabel).toBe('目录无记录')
    expect(rows[1].readyLabel).toBe('配置未就绪')
    expect(rows[1].configuredSource).toBe('TickFlow')
  })
})

describe('classifyMarginQueryError', () => {
  it('distinguishes missing file, empty-unrelated read errors and bad symbols', () => {
    expect(classifyMarginQueryError(new Error('offline margin file not found for 000001.SZ'))).toBe('not_found')
    expect(classifyMarginQueryError(new Error('offline_quantdb root is not configured'))).toBe('unconfigured')
    expect(classifyMarginQueryError(new Error('offline margin file missing columns: time'))).toBe('invalid_schema')
    expect(classifyMarginQueryError(new Error('offline margin file unreadable for 000001.SZ'))).toBe('unreadable')
    expect(classifyMarginQueryError(new Error('invalid A-share symbol: ../secret'))).toBe('invalid_request')
    expect(marginQueryErrorLabel('empty')).toContain('没有记录')
    expect(formatMissingValue(null)).toBe('—')
    expect(displaySourceName('same_as_daily')).toBe('跟随日K')
  })
})
