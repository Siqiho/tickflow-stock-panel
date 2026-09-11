import { expect, it } from 'vitest'
import { normalizeHermesChartPoints, parseHermesRichContent } from '../hermesRichContent'

it('keeps ordinary assistant text as a markdown block', () => {
  expect(parseHermesRichContent('市场整体偏暖。')).toEqual([
    { type: 'markdown', text: '市场整体偏暖。' },
  ])
})

it('extracts a reserved chart spec without treating other json as html', () => {
  const content = [
    '## 结论',
    '资金流入占优。',
    '```json',
    '{"type":"chart","template":"F1","view":"rung-bars","as_of":"2026-08-17","source":"market_overview","title":"主力净流入","points":[{"label":"光通信","value":63.08},{"label":"CPO","value":38.8}]}',
    '```',
  ].join('\n')

  const blocks = parseHermesRichContent(content)
  expect(blocks[0]).toEqual({ type: 'markdown', text: '## 结论\n资金流入占优。' })
  expect(blocks[1]?.type).toBe('chart')
  if (blocks[1]?.type !== 'chart') return
  expect(normalizeHermesChartPoints(blocks[1].spec)).toEqual([
    { label: '光通信', value: 63.08 },
    { label: 'CPO', value: 38.8 },
  ])
})
