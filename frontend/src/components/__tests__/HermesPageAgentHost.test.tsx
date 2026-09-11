import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HermesPageAgentHost } from '@/components/HermesPageAgentHost'
import { clearPageContext, setPageContext } from '@/lib/pageContext'

vi.mock('@/pages/HermesAgentChat', () => ({
  HermesAgentChat: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="embedded-hermes">{embedded ? 'embedded' : 'full'}</div>
  ),
}))

afterEach(() => {
  clearPageContext()
})

describe('HermesPageAgentHost', () => {
  it('shows a floating entry on sample pages and opens the embedded agent', () => {
    setPageContext({
      route: '/limit-ladder',
      title: '连板梯队',
      summary: '样板页',
      items: [],
    })
    const onOpenChange = vi.fn()
    render(
      <MemoryRouter initialEntries={['/limit-ladder']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/limit-ladder" element={<HermesPageAgentHost open={false} onOpenChange={onOpenChange} />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: '打开 连板梯队 的 AI 助理' }))
    expect(onOpenChange).toHaveBeenCalledWith(true)
  })

  it('opens a new conversation window instead of restoring the last chat', () => {
    setPageContext({
      route: '/concept-analysis',
      title: '概念分析',
      summary: '样板页',
      items: [],
    })
    const onOpenChange = vi.fn()
    const { rerender } = render(
      <MemoryRouter initialEntries={['/concept-analysis']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/concept-analysis" element={<HermesPageAgentHost open={false} onOpenChange={onOpenChange} />} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: '打开 概念分析 的 AI 助理' }))
    expect(onOpenChange).toHaveBeenCalledWith(true)
    rerender(
      <MemoryRouter initialEntries={['/concept-analysis']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/concept-analysis" element={<HermesPageAgentHost open onOpenChange={onOpenChange} />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('embedded-hermes')).toHaveTextContent('embedded')
    expect(screen.queryByRole('button', { name: '打开 概念分析 的 AI 助理' })).not.toBeInTheDocument()
  })

  it('hides the floating entry on the full Hermes page', () => {
    render(
      <MemoryRouter initialEntries={['/ai/hermes']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/ai/hermes" element={<HermesPageAgentHost open={false} onOpenChange={() => undefined} />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByRole('button', { name: /打开/ })).not.toBeInTheDocument()
  })

  it('closes the embedded agent from the title-bar close button', () => {
    setPageContext({
      route: '/industry-analysis',
      title: '行业分析',
      summary: '样板页',
      items: [],
    })
    const onOpenChange = vi.fn()
    render(
      <MemoryRouter initialEntries={['/industry-analysis']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/industry-analysis" element={<HermesPageAgentHost open onOpenChange={onOpenChange} />} />
        </Routes>
      </MemoryRouter>,
    )

    const closeButton = screen.getByRole('button', { name: '关闭嵌入 AI 助理' })
    fireEvent.pointerDown(closeButton, { button: 0, clientX: 1200, clientY: 24 })
    fireEvent.click(closeButton)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('lets the user drag the open panel by its title bar', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 })
    setPageContext({
      route: '/industry-analysis',
      title: '行业分析',
      summary: '样板页',
      items: [],
    })
    render(
      <MemoryRouter initialEntries={['/industry-analysis']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/industry-analysis" element={<HermesPageAgentHost open onOpenChange={() => undefined} />} />
        </Routes>
      </MemoryRouter>,
    )

    const dialog = screen.getByRole('dialog', { name: '嵌入 AI 助理' })
    const handle = screen.getByTitle('拖动标题栏可移动窗口')
    const readX = () => Number.parseFloat((dialog.style.transform.match(/translate3d\(([-\d.]+)px/) ?? ['0', '0'])[1])
    const startLeft = readX()
    fireEvent.pointerDown(handle, { button: 0, clientX: 800, clientY: 40 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 500, clientY: 180, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 500, clientY: 180, bubbles: true }))
    expect(readX()).toBeLessThan(startLeft)
  })

  it('lets the user resize the open panel from an edge handle', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 })
    setPageContext({
      route: '/industry-analysis',
      title: '行业分析',
      summary: '样板页',
      items: [],
    })
    render(
      <MemoryRouter initialEntries={['/industry-analysis']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/industry-analysis" element={<HermesPageAgentHost open onOpenChange={() => undefined} />} />
        </Routes>
      </MemoryRouter>,
    )
    const dialog = screen.getByRole('dialog', { name: '嵌入 AI 助理' })
    const handle = dialog.querySelector('[data-resize-edge="se"]') as HTMLElement
    const startWidth = Number.parseFloat(dialog.style.width)
    fireEvent.mouseDown(handle, { button: 0, clientX: 1200, clientY: 700 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 1080, clientY: 620, bubbles: true }))
    const midWidth = Number.parseFloat(dialog.style.width)
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 1080, clientY: 620, bubbles: true }))
    expect(midWidth).toBeLessThan(startWidth)
    expect(Number.parseFloat(dialog.style.width)).toBeLessThan(startWidth)
  })

  it('does not show the floating entry on pages without a snapshot', () => {
    render(
      <MemoryRouter initialEntries={['/watchlist']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/watchlist" element={<HermesPageAgentHost open={false} onOpenChange={() => undefined} />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByRole('button', { name: /打开/ })).not.toBeInTheDocument()
  })
})
