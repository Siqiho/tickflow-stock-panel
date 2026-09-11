import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { StrategyBuilderDialog } from '@/components/screener/StrategyBuilderDialog'
import { api } from '@/lib/api'


beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api, 'strategyAiStatus').mockResolvedValue({ configured: true, has_key: true, has_model: true })
})


afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})


it('uses the routed stock as the seed for a new AI strategy', async () => {
  render(
    <StrategyBuilderDialog
      open
      onClose={() => undefined}
      stockContext={{ symbol: '300502.SZ', name: '新易盛' }}
    />,
  )

  expect(await screen.findByDisplayValue('新易盛特征策略')).toBeInTheDocument()
  expect(screen.getByDisplayValue('以新易盛（300502.SZ）为参考标的生成可复用选股策略')).toBeInTheDocument()
  expect(screen.getByDisplayValue('参考新易盛（300502.SZ）的走势、量价与技术指标特征，提炼可泛化的选股条件；不要把策略限定为只匹配这一只股票。')).toBeInTheDocument()
})
