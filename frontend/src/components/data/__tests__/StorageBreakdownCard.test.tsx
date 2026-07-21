import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StorageBreakdownCard } from '../StorageBreakdownCard'
import { storageFixture } from './catalogFixtures'

describe('StorageBreakdownCard', () => {
  it('uses backend totals directly even when category values are deliberately inconsistent', () => {
    render(<StorageBreakdownCard storage={storageFixture} refreshedAt="2026-07-21T08:31:00Z" />)

    expect(screen.getByTestId('managed-storage')).toHaveTextContent('1000 B')
    expect(screen.getByTestId('operational-storage')).toHaveTextContent('200 B')
    expect(screen.getByTestId('total-storage')).toHaveTextContent('9.8 KiB')
    expect(screen.getByTestId('total-storage')).not.toHaveTextContent('75 B')
    expect(screen.getByText('2026-07-21T08:31:00Z')).toBeInTheDocument()
  })

  it('marks stale storage explicitly', () => {
    render(<StorageBreakdownCard storage={storageFixture} isStale />)
    expect(screen.getByText('状态可能过期')).toBeInTheDocument()
  })
})
