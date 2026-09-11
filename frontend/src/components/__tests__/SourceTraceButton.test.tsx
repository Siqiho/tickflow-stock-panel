import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import { SourceTraceButton } from '@/components/SourceTraceButton'
import { SOURCE_TRACE } from '@/lib/sourceTraceSubjects'
import { QK } from '@/lib/queryKeys'

function renderButton(isAdmin: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(QK.settings, { is_admin: isAdmin, mode: 'api_key' })
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SourceTraceButton subjects={SOURCE_TRACE.conceptFundFlow} />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  // keep isolated
})

it('hides source tracing from ordinary users', () => {
  renderButton(false)
  expect(screen.queryByRole('link', { name: /来源追踪/ })).not.toBeInTheDocument()
})

it('lets administrators open the matching data-platform subject', () => {
  renderButton(true)
  const link = screen.getByRole('link', { name: /来源追踪：概念资金流快照/ })
  expect(link).toHaveAttribute('href', '/data?section=source-trace&trace=ext_fund_flow_concept')
})
