import { describe, expect, it } from 'vitest'

import type { ColumnConfig } from '@/lib/list-columns'
import { getSortValue } from '@/lib/stock-table'


describe('getSortValue financial columns', () => {
  it.each([
    ['eps', 2.8],
    ['bps', 20.5],
    ['roe', 0.1452],
    ['pe_ttm', 32.1],
    ['pb', 4.2],
    ['gross_margin', 0.47],
    ['net_margin', 0.333],
    ['revenue_yoy', 1.058],
    ['net_income_yoy', 0.768],
    ['debt_ratio', 0.31],
  ])('returns %s for sorting and filtering', (key, value) => {
    const column: ColumnConfig = {
      id: `builtin:${key}`,
      source: { type: 'builtin', key },
      label: key,
      visible: true,
    }

    expect(getSortValue({ [key]: value }, column)).toBe(value)
  })
})
