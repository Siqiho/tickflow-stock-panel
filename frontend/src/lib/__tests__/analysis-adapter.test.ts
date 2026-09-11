import { describe, expect, it } from 'vitest'
import type { ExtDataConfig, ExtDataField } from '../api'
import {
  hasCandidateDimensionField,
  isUsableDimensionField,
  normalizeMarketSnapshotPctRows,
  pickBestDimensionConfig,
  pickDimensionField,
  percentPointsToRatio,
  resolveDimension,
  resolveDimensionConfigId,
} from '../analysis-adapter'

const INDUSTRY_FIELDS = ['industry', '行业', 'sector', '申万', '中信', '行业名称', 'industry_name', 'sector_name']

function config(id: string, label: string, fields: ExtDataField[]): ExtDataConfig {
  return {
    id,
    label,
    mode: 'snapshot',
    fields,
    created_at: '2026-08-07T00:00:00',
    updated_at: '2026-08-07T00:00:00',
  }
}

const fundFlowConfig = config('ext_fund_flow_bk', '行业板块资金流', [
  { name: 'code', dtype: 'string', label: '代码' },
  { name: 'name', dtype: 'string', label: '名称' },
  { name: 'main_net', dtype: 'float', label: '主力净流入' },
  { name: 'change_pct', dtype: 'float', label: '涨跌幅' },
  { name: 'as_of', dtype: 'string', label: '日期' },
])

const industryConfig = config('ext_hy_ths', '扩展行业', [
  { name: 'symbol', dtype: 'string', label: '标的代码' },
  { name: '股票简称', dtype: 'string', label: '股票简称' },
  { name: '所属同花顺行业', dtype: 'string', label: '所属同花顺行业' },
])

describe('industry dimension source selection', () => {
  it('rejects a fund-flow table even when its label contains 行业', () => {
    expect(hasCandidateDimensionField(fundFlowConfig, INDUSTRY_FIELDS)).toBe(false)
    expect(hasCandidateDimensionField(industryConfig, INDUSTRY_FIELDS)).toBe(true)
  })

  it('prefers the built-in stock-to-industry membership table over an earlier fund-flow table', () => {
    expect(
      pickBestDimensionConfig(
        [fundFlowConfig, industryConfig],
        INDUSTRY_FIELDS,
        ['ext_hy_ths'],
      ),
    ).toBe('ext_hy_ths')
  })

  it('ignores a persisted fund-flow selection but keeps a valid custom industry selection', () => {
    const customIndustryConfig = config('custom_sw_industry', '申万行业分类', [
      { name: 'symbol', dtype: 'string', label: '标的代码' },
      { name: 'sw_industry_name', dtype: 'string', label: '申万行业名称' },
    ])
    const configs = [fundFlowConfig, industryConfig, customIndustryConfig]

    expect(
      resolveDimensionConfigId(configs, 'ext_fund_flow_bk', INDUSTRY_FIELDS, ['ext_hy_ths']),
    ).toBe('ext_hy_ths')
    expect(
      resolveDimensionConfigId(configs, 'custom_sw_industry', INDUSTRY_FIELDS, ['ext_hy_ths']),
    ).toBe('custom_sw_industry')
  })

  it('never accepts numeric money or percentage fields as a grouping dimension', () => {
    const mainNet = fundFlowConfig.fields.find(field => field.name === 'main_net')!
    expect(isUsableDimensionField(mainNet)).toBe(false)
    expect(isUsableDimensionField({ name: '所属同花顺行业', label: '所属同花顺行业' } as ExtDataField)).toBe(true)
    expect(isUsableDimensionField({ name: 'as_of', label: '日期', dtype: 'string' })).toBe(false)
    expect(pickDimensionField(fundFlowConfig.fields, ['main_net', ...INDUSTRY_FIELDS])).not.toBe('main_net')
    expect(pickDimensionField(industryConfig.fields, INDUSTRY_FIELDS)).toBe('所属同花顺行业')
  })

  it('normalizes market-snapshot percentage points before ratio-based display and scoring', () => {
    expect(percentPointsToRatio(4.0978750804893815)).toBeCloseTo(0.040978750804893815)
    expect(percentPointsToRatio(-2.4363145782080844)).toBeCloseTo(-0.024363145782080844)
    expect(percentPointsToRatio(null)).toBeNull()

    const percentPointRows = [
      { symbol: 'A', change_pct: 4.0978750804893815 },
      { symbol: 'B', change_pct: 10.001923446816686 },
      { symbol: 'C', change_pct: -2.4363145782080844 },
      { symbol: 'D', change_pct: 0.5 },
    ]
    const ratioRows = [
      { symbol: 'A', change_pct: 0.040978750804893815 },
      { symbol: 'B', change_pct: 0.10001923446816686 },
      { symbol: 'C', change_pct: -0.024363145782080844 },
      { symbol: 'D', change_pct: 0.005 },
    ]

    expect(normalizeMarketSnapshotPctRows(percentPointRows)).toEqual(ratioRows)
    expect(normalizeMarketSnapshotPctRows(ratioRows)).toEqual(ratioRows)
  })
})

const CONCEPT_FIELDS = ['concept', '概念', 'theme', '题材', '板块', 'concept_name', '概念名称', '所属概念']

const conceptFundFlowConfig = config('ext_fund_flow_concept', '概念板块资金流', [
  { name: 'code', dtype: 'string', label: '代码' },
  { name: 'name', dtype: 'string', label: '名称' },
  { name: 'main_net', dtype: 'float', label: '主力净流入' },
  { name: 'change_pct', dtype: 'float', label: '涨跌幅' },
  { name: 'as_of', dtype: 'string', label: '日期' },
])

const conceptConfig = config('ext_gn_ths', '扩展概念', [
  { name: 'symbol', dtype: 'string', label: '标的代码' },
  { name: '股票简称', dtype: 'string', label: '股票简称' },
  { name: '所属概念', dtype: 'string', label: '所属概念' },
])

describe('concept dimension source selection', () => {
  it('rejects a concept fund-flow snapshot even when its label contains 概念', () => {
    expect(hasCandidateDimensionField(conceptFundFlowConfig, CONCEPT_FIELDS)).toBe(false)
    expect(hasCandidateDimensionField(conceptConfig, CONCEPT_FIELDS)).toBe(true)
  })

  it('prefers the built-in stock-to-concept membership table over an earlier fund-flow table', () => {
    expect(
      pickBestDimensionConfig(
        [conceptFundFlowConfig, conceptConfig],
        CONCEPT_FIELDS,
        ['ext_gn_ths'],
      ),
    ).toBe('ext_gn_ths')
  })

  it('ignores a persisted fund-flow or as_of selection but keeps a valid custom concept selection', () => {
    const customConceptConfig = config('custom_theme_map', '题材分类', [
      { name: 'symbol', dtype: 'string', label: '标的代码' },
      { name: 'theme_name', dtype: 'string', label: '题材名称' },
    ])
    const configs = [conceptFundFlowConfig, conceptConfig, customConceptConfig]

    expect(
      resolveDimensionConfigId(configs, 'ext_fund_flow_concept', CONCEPT_FIELDS, ['ext_gn_ths']),
    ).toBe('ext_gn_ths')
    expect(
      resolveDimensionConfigId(configs, 'custom_theme_map', CONCEPT_FIELDS, ['ext_gn_ths']),
    ).toBe('custom_theme_map')
    expect(pickDimensionField(conceptFundFlowConfig.fields, CONCEPT_FIELDS)).not.toBe('as_of')
    expect(pickDimensionField(conceptConfig.fields, CONCEPT_FIELDS)).toBe('所属概念')
  })

  it('does not split a fund-flow as_of timestamp into fake concept groups', () => {
    const result = resolveDimension(
      {
        id: conceptFundFlowConfig.id,
        label: conceptFundFlowConfig.label,
        mode: 'snapshot',
        date: '2026-08-20',
        total: 2,
        limit: 2,
        fields: conceptFundFlowConfig.fields,
        rows: [
          { code: 'BK1106', name: '创新药', main_net: 6261482496, change_pct: 4.85, as_of: '2026-08-20 16:16:02' },
          { code: 'BK0547', name: '黄金概念', main_net: 5918791168, change_pct: 2.17, as_of: '2026-08-20 16:16:02' },
        ],
      },
      conceptFundFlowConfig,
      CONCEPT_FIELDS,
    )
    expect(result.groups.map(group => group.key)).not.toEqual(expect.arrayContaining(['2026-08-20', '16:16:02']))
  })
})
