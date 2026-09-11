import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ResizableAnalysisLayout } from '@/components/stock-analysis/ResizableAnalysisLayout'

afterEach(() => {
  vi.unstubAllGlobals()
})

it('resizes the analysis rail by dragging the divider', () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  render(
    <ResizableAnalysisLayout
      main={<section>主分析区</section>}
      rail={<aside>辅助分析区</aside>}
    />,
  )

  const divider = screen.getByRole('separator', { name: '调整辅助分析栏宽度' })
  fireEvent.pointerDown(divider, { button: 0, pointerId: 1, clientX: 800 })
  fireEvent.pointerMove(window, { pointerId: 1, clientX: 740 })

  expect(divider).toHaveAttribute('aria-valuenow', '356')
  expect(screen.getByTestId('stock-analysis-layout')).toHaveStyle({
    '--stock-analysis-rail-width': '356px',
  })

  fireEvent.pointerUp(window, { pointerId: 1 })
  expect(document.body.style.cursor).toBe('')
})

it('supports keyboard resizing and width limits', () => {
  render(
    <ResizableAnalysisLayout
      main={<section>主分析区</section>}
      rail={<aside>辅助分析区</aside>}
    />,
  )

  const divider = screen.getByRole('separator', { name: '调整辅助分析栏宽度' })

  fireEvent.keyDown(divider, { key: 'ArrowLeft' })
  expect(divider).toHaveAttribute('aria-valuenow', '320')

  fireEvent.keyDown(divider, { key: 'Home' })
  expect(divider).toHaveAttribute('aria-valuenow', '280')

  fireEvent.keyDown(divider, { key: 'End' })
  expect(divider).toHaveAttribute('aria-valuenow', '520')

  fireEvent.doubleClick(divider)
  expect(divider).toHaveAttribute('aria-valuenow', '296')
})

it('clamps the rail to the space left by the main chart', () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  render(
    <ResizableAnalysisLayout
      main={<section>主分析区</section>}
      rail={<aside>辅助分析区</aside>}
    />,
  )

  const layout = screen.getByTestId('stock-analysis-layout')
  vi.spyOn(layout, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 992,
    bottom: 800,
    width: 992,
    height: 800,
    toJSON: () => ({}),
  })
  fireEvent.resize(window)

  const divider = screen.getByRole('separator', { name: '调整辅助分析栏宽度' })
  expect(divider).toHaveAttribute('aria-valuemax', '336')

  fireEvent.keyDown(divider, { key: 'End' })
  expect(divider).toHaveAttribute('aria-valuenow', '336')

  fireEvent.pointerDown(divider, { button: 0, pointerId: 2, clientX: 800 })
  fireEvent.pointerMove(window, { pointerId: 2, clientX: 600 })
  expect(divider).toHaveAttribute('aria-valuenow', '336')
})
