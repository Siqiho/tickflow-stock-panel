import { describe, expect, it } from 'vitest'
import {
  applySavedNavOrder,
  collapseNavOrder,
  firstVisibleMemberPath,
  isCatalogEntryVisible,
  isGroupHidden,
  permissionFromSettings,
  pinAdminBeforeData,
  QUANT_GROUP,
  QUANT_PATH,
  TRADE_GROUP,
  TRADE_PATH,
  toggleHiddenIds,
  visibleMembers,
} from '../navGroups'

const admin = { settingsReady: true, isAdmin: true }
const user = { settingsReady: true, isAdmin: false }
const loading = { settingsReady: false, isAdmin: false }

describe('nav group preference compatibility', () => {
  it('collapses legacy member order so each group appears once', () => {
    expect(collapseNavOrder([
      '/screener',
      '/watchlist',
      '/backtest',
      '/trading',
      '/monitor',
      '/ai',
    ])).toEqual(['/quant', '/watchlist', '/trade', '/ai'])
  })

  it('maps a saved /trading hide to the trading page only, not the whole group', () => {
    const hidden = new Set(['/trading'])
    expect(isGroupHidden(TRADE_GROUP, hidden, admin)).toBe(false)
    expect(isCatalogEntryVisible(TRADE_PATH, hidden, admin)).toBe(true)
    expect(visibleMembers(TRADE_GROUP, hidden, admin).map(item => item.path)).toEqual([
      '/monitor',
      '/lots',
      '/signals',
      '/abnormal',
    ])
  })

  it('hides the trade group when every allowed member is hidden or the new group id is hidden', () => {
    expect(isGroupHidden(
      TRADE_GROUP,
      new Set(['/monitor', '/lots', '/signals', '/abnormal', '/trading']),
      admin,
    )).toBe(true)
    expect(isGroupHidden(TRADE_GROUP, new Set([TRADE_PATH]), admin)).toBe(true)
    expect(isGroupHidden(
      TRADE_GROUP,
      new Set(['/lots', '/signals', '/abnormal', '/trading']),
      user,
    )).toBe(true)
  })

  it('restores a fully hidden group without rewriting unrelated ids', () => {
    const restored = toggleHiddenIds(
      ['/lots', '/signals', '/abnormal', '/trading', '/ai'],
      TRADE_PATH,
      user,
    )
    expect(restored).toEqual(['/ai'])
  })

  it('keeps admin monitor out of tabs until settings resolve', () => {
    expect(visibleMembers(TRADE_GROUP, new Set(), loading).map(item => item.path)).not.toContain('/monitor')
    expect(visibleMembers(TRADE_GROUP, new Set(), user).map(item => item.path)).not.toContain('/monitor')
    expect(visibleMembers(TRADE_GROUP, new Set(), admin)[0]?.path).toBe('/monitor')
    expect(firstVisibleMemberPath(TRADE_GROUP, new Set(), user)).toBe('/lots')
    expect(firstVisibleMemberPath(TRADE_GROUP, new Set(), admin)).toBe('/monitor')
    expect(firstVisibleMemberPath(QUANT_GROUP, new Set(), admin)).toBe('/screener')
  })

  it('applies collapsed saved order and appends unseen catalog entries', () => {
    const items = [
      { id: '/', label: '看板' },
      { id: QUANT_PATH, label: '量化' },
      { id: '/watchlist', label: '自选' },
      { id: TRADE_PATH, label: '交易' },
    ]
    expect(applySavedNavOrder(items, ['/screener', '/trading', '/watchlist']).map(item => item.id)).toEqual([
      QUANT_PATH,
      TRADE_PATH,
      '/watchlist',
      '/',
    ])
  })

  it('pins admin, data, then news at the end for administrators', () => {
    const items = [
      { to: '/news', label: '资讯' },
      { to: '/ai', label: 'AI' },
      { to: '/data', label: '数据' },
      { to: '/admin/users', label: '用户管理' },
    ]
    expect(pinAdminBeforeData(items, true).map(item => item.to)).toEqual([
      '/ai',
      '/admin/users',
      '/data',
      '/news',
    ])
    expect(pinAdminBeforeData(items, false).map(item => item.to)).toEqual([
      '/news',
      '/ai',
      '/data',
      '/admin/users',
    ])
  })

  it('treats missing settings as non-admin', () => {
    expect(permissionFromSettings(undefined)).toEqual(loading)
    expect(permissionFromSettings({ is_admin: false })).toEqual(user)
    expect(permissionFromSettings({ is_admin: true })).toEqual(admin)
  })
})
