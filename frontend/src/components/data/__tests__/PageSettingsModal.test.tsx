import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { getCardVisibility, PageSettingsModal } from '../PageSettingsModal'

describe('PageSettingsModal', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows every catalog group by default without consulting capabilities', () => {
    expect(getCardVisibility(undefined)).toMatchObject({
      instruments: true,
      daily: true,
      adj_factor: true,
      enriched: true,
      index: true,
      etf: true,
      minute: true,
      financials: true,
      f10: true,
    })
  })

  it('restores ETF and financials visibility and explains the rendering-only boundary', () => {
    localStorage.setItem('data-card-visible', JSON.stringify({ etf: false, financials: false }))
    render(<PageSettingsModal caps={undefined} />)

    expect(screen.getByText(/只影响目录渲染/)).toBeInTheDocument()
    expect(screen.getByText(/不影响数据或请求/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '恢复默认' }))

    expect(screen.getByRole('checkbox', { name: '显示 ETF' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('checkbox', { name: '显示 财务数据' })).toHaveAttribute('aria-checked', 'true')
    expect(getCardVisibility(undefined).etf).toBe(true)
    expect(getCardVisibility(undefined).financials).toBe(true)
  })
})
