import type { FundFlowWindowResponse } from '@/lib/api'

type IndustryFreshness = Pick<
  FundFlowWindowResponse,
  'data_as_of' | 'freshness_status' | 'freshness_note' | 'expected_trading_day' | 'calendar_covers'
>

type FreshnessStatus = NonNullable<FundFlowWindowResponse['freshness_status']>
type StatusOk = FreshnessStatus extends 'fresh' | 'stale' | 'unknown'
  ? ('fresh' | 'stale' | 'unknown') extends FreshnessStatus
    ? true
    : never
  : never

const _status: StatusOk = true
const _fields: IndustryFreshness = {
  data_as_of: '2026-08-31',
  freshness_status: 'fresh',
  freshness_note: '足够新',
  expected_trading_day: '2026-08-31',
  calendar_covers: true,
}

void _status
void _fields
