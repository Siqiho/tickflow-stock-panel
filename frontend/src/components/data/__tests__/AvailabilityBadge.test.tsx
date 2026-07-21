import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AvailabilityBadge } from '../AvailabilityBadge'

describe('AvailabilityBadge', () => {
  it.each([
    ['provider_supported', true, '数据源支持：是'],
    ['entitled', false, '当前有权限：否'],
    ['local_materialized', true, '本地已落库：是'],
    ['serving_ready', false, '当前可服务：否'],
  ] as const)('renders %s as explicit text and an accessible state', (kind, value, name) => {
    render(<AvailabilityBadge kind={kind} value={value} />)

    const badge = screen.getByLabelText(name)
    expect(badge).toHaveTextContent(value ? '是' : '否')
    expect(badge.querySelector('svg')).toBeInTheDocument()
  })
})
