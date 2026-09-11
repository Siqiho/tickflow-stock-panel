import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Eye,
  ExternalLink,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  UserRound,
  UsersRound,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import {
  api,
  type AdminUserStrategySummary,
  type AdminUserSummary,
  type AdminUsersPayload,
  type HermesMessage,
  type HermesSession,
} from '@/lib/api'
import { cn } from '@/lib/cn'

function formatEpoch(value?: number | null) {
  if (!value) return '暂无'
  const milliseconds = value < 1_000_000_000_000 ? value * 1000 : value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(milliseconds))
}

function accountStatusLabel(status: string) {
  return status === 'active' ? '账号正常' : '账号停用'
}

function sessionTitle(session: HermesSession) {
  return session.title?.trim() || session.preview?.trim() || '未命名对话'
}

export function AdminUsers() {
  const [payload, setPayload] = useState<AdminUsersPayload | null>(null)
  const [selectedUserId, setSelectedUserId] = useState('')
  const [sessions, setSessions] = useState<HermesSession[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [messages, setMessages] = useState<HermesMessage[]>([])
  const [userStrategies, setUserStrategies] = useState<AdminUserStrategySummary[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [loadingStrategies, setLoadingStrategies] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.adminUsers()
      .then(usersResult => {
        if (cancelled) return
        setPayload(usersResult)
        setSelectedUserId(
          usersResult.users.find(user => user.role === 'user')?.id ?? '',
        )
      })
      .catch(cause => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : '无法读取用户管理数据')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const users = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return payload?.users ?? []
    return (payload?.users ?? []).filter(user =>
      user.username.toLowerCase().includes(needle)
      || user.id.toLowerCase().includes(needle)
      || (user.profile_name ?? '').toLowerCase().includes(needle),
    )
  }, [payload, search])

  const selectedUser = payload?.users.find(user => user.id === selectedUserId) ?? null
  const selectedSession = sessions.find(session => session.id === selectedSessionId) ?? null
  const summaryCards = [
    { label: '全部账户', value: payload?.summary.total_accounts ?? 0, icon: UsersRound },
    { label: '普通用户', value: payload?.summary.regular_users ?? 0, icon: UserRound },
    { label: '今日 AI 活跃', value: payload?.summary.active_users_today ?? 0, icon: CheckCircle2 },
    { label: '今日 AI 请求', value: payload?.summary.ai_requests_today ?? 0, icon: Bot },
    { label: 'Profile 就绪', value: payload?.summary.profiles_ready ?? 0, icon: ShieldCheck },
  ]

  const selectUser = (user: AdminUserSummary) => {
    if (user.role !== 'user' || user.status !== 'active') return
    setSelectedUserId(user.id)
    setSessions([])
    setSelectedSessionId('')
    setMessages([])
    setUserStrategies([])
    setError('')
  }

  const loadStrategies = async () => {
    if (!selectedUser) return
    setLoadingStrategies(true)
    setError('')
    try {
      const result = await api.adminUserStrategies(selectedUser.id)
      setUserStrategies(result.strategies)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法读取该用户的策略')
    } finally {
      setLoadingStrategies(false)
    }
  }

  const loadSessions = async () => {
    if (!selectedUser) return
    setLoadingSessions(true)
    setError('')
    setSelectedSessionId('')
    setMessages([])
    try {
      const result = await api.adminUserSessions(selectedUser.id)
      setSessions(result.sessions)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法读取该用户的历史对话')
    } finally {
      setLoadingSessions(false)
    }
  }

  const loadMessages = async (session: HermesSession) => {
    if (!selectedUser) return
    setSelectedSessionId(session.id)
    setLoadingMessages(true)
    setMessages([])
    setError('')
    try {
      const result = await api.adminUserMessages(
        selectedUser.id,
        session.id,
      )
      setMessages(result.messages)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法读取对话内容')
    } finally {
      setLoadingMessages(false)
    }
  }

  if (loading) {
    return (
      <div className="grid min-h-[60vh] place-items-center text-sm text-muted">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />读取管理员数据…
      </div>
    )
  }

  return (
    <>
      <PageHeader
        title="用户管理"
        subtitle="查看账户、AI 使用状况、历史对话与个人策略。"
      />

      <div className="space-y-5 px-4 py-4 sm:px-6 md:px-8 md:py-6">
        {error && (
          <div role="alert" className="flex items-center gap-2 rounded-btn bg-danger/10 px-3 py-2 text-xs text-danger">
            <AlertTriangle className="h-4 w-4" />{error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {summaryCards.map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-card border border-border bg-surface p-3.5">
              <div className="flex items-center gap-2 text-xs text-muted">
                <Icon className="h-3.5 w-3.5" />{label}
              </div>
              <div className="mt-2 font-mono text-xl font-semibold text-foreground">{value}</div>
            </div>
          ))}
        </div>

        <div className="grid gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <section className="overflow-hidden rounded-card border border-border bg-surface">
            <div className="border-b border-border p-3">
              <div className="text-sm font-medium text-foreground">账户</div>
              <label className="mt-2 flex items-center gap-2 rounded-btn border border-border bg-base px-2.5 py-2">
                <Search className="h-3.5 w-3.5 text-muted" />
                <input
                  value={search}
                  onChange={event => setSearch(event.target.value)}
                  placeholder="搜索用户名、ID 或 Profile"
                  className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none"
                />
              </label>
            </div>
            <div className="max-h-[42rem] divide-y divide-border overflow-y-auto">
              {users.map(user => (
                <button
                  key={user.id}
                  type="button"
                  disabled={user.role === 'admin' || user.status !== 'active'}
                  onClick={() => selectUser(user)}
                  className={cn(
                    'w-full p-3 text-left transition-colors',
                    user.id === selectedUserId ? 'bg-accent/10' : 'hover:bg-elevated/60',
                    (user.role === 'admin' || user.status !== 'active') && 'cursor-default opacity-75',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-foreground">{user.username}</span>
                    <span className="flex shrink-0 items-center gap-1">
                      <span className={cn(
                        'rounded-full px-2 py-0.5 text-[10px]',
                        user.role === 'admin' ? 'bg-purple-500/15 text-purple-400' : 'bg-accent/10 text-accent',
                      )}>
                        {user.role === 'admin' ? '管理员' : '用户'}
                      </span>
                      <span className={cn(
                        'rounded-full px-2 py-0.5 text-[10px]',
                        user.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500',
                      )}>
                        {accountStatusLabel(user.status)}
                      </span>
                    </span>
                  </div>
                  <div className="mt-1 truncate font-mono text-[10px] text-muted">{user.profile_name || '尚无 Profile'}</div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] text-secondary">
                    <span>今日请求 {user.ai_requests_today}</span>
                    <span>近 7 日 {user.ai_requests_7d}</span>
                    <span>对话 {user.conversation_count ?? '--'}{user.conversation_count_capped ? '+' : ''}</span>
                    <span>策略 {user.strategy_count ?? 0}</span>
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="min-w-0 space-y-4">
            {selectedUser ? (
              <>
                <div className="rounded-card border border-border bg-surface p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-base font-semibold text-foreground">{selectedUser.username}</h2>
                        <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent">普通用户</span>
                        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-500">
                          {accountStatusLabel(selectedUser.status)}
                        </span>
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-muted">{selectedUser.id}</div>
                    </div>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1 text-xs text-secondary sm:grid-cols-3">
                      <span>注册：{formatEpoch(selectedUser.created_at)}</span>
                      <span>最近登录：{formatEpoch(selectedUser.last_login_at)}</span>
                      <span>最近对话：{formatEpoch(selectedUser.last_conversation_at)}</span>
                      <span>登录会话：{selectedUser.active_login_sessions}</span>
                      <span>今日额度：{selectedUser.ai_requests_today}/{selectedUser.ai_daily_limit ?? '∞'}</span>
                      <span>Profile：{selectedUser.profile_status ?? '未分配'}</span>
                      <span>个人策略：{selectedUser.strategy_count ?? 0}</span>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
                    <span className="text-[10px] text-muted">只读查看该用户与 AI 的历史对话，不提供代发、修改或删除操作。</span>
                    <button
                      type="button"
                      disabled={loadingSessions || selectedUser.profile_status !== 'ready'}
                      onClick={loadSessions}
                      className="inline-flex h-9 items-center gap-2 rounded-btn bg-accent px-3 text-xs font-medium text-white disabled:opacity-45"
                    >
                      {loadingSessions ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Eye className="h-3.5 w-3.5" />}
                      读取历史对话
                    </button>
                  </div>
                </div>

                <section className="overflow-hidden rounded-card border border-border bg-surface">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
                    <div>
                      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                        <Sparkles className="h-4 w-4 text-purple-400" />用户策略
                        <span className="rounded-full bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-400">{selectedUser.strategy_count ?? 0}</span>
                      </div>
                      <p className="mt-1 text-[10px] text-muted">管理员只读查看，并可在自己的回测空间中运行；不能替用户修改或删除。</p>
                    </div>
                    <button
                      type="button"
                      onClick={loadStrategies}
                      disabled={loadingStrategies}
                      className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border bg-base px-3 text-xs text-secondary hover:border-accent/40 hover:text-accent disabled:opacity-45"
                    >
                      {loadingStrategies ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Eye className="h-3.5 w-3.5" />}
                      读取用户策略
                    </button>
                  </div>
                  <div className="grid gap-3 p-4 md:grid-cols-2">
                    {userStrategies.length === 0 ? (
                      <div className="col-span-full py-4 text-center text-xs text-muted">
                        {loadingStrategies ? '正在读取…' : (selectedUser.strategy_count ?? 0) > 0 ? '点击“读取用户策略”查看' : '该用户尚未保存策略'}
                      </div>
                    ) : userStrategies.map(strategy => (
                      <article key={strategy.id} className="rounded-btn border border-border bg-base/50 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-foreground">{strategy.name}</div>
                            <div className="mt-0.5 truncate font-mono text-[10px] text-muted">{strategy.id}</div>
                          </div>
                          <span className="shrink-0 rounded-full bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-400">
                            {strategy.source === 'ai' ? 'AI' : '自定义'}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-secondary">{strategy.description || strategy.rules}</p>
                        <div className="mt-3 flex items-center justify-between gap-2">
                          <span className="text-[10px] text-muted">更新 {new Date(strategy.updated_at).toLocaleString('zh-CN')}</span>
                          <a
                            href={`/backtest?strategy_id=${encodeURIComponent(strategy.id)}&strategy_owner_user_id=${encodeURIComponent(selectedUser.id)}`}
                            className="inline-flex items-center gap-1 rounded-btn bg-accent/10 px-2.5 py-1.5 text-[10px] font-medium text-accent hover:bg-accent/15"
                          >
                            管理员回测 <ExternalLink className="h-3 w-3" />
                          </a>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>

                <div className="grid min-h-[28rem] gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
                  <div className="overflow-hidden rounded-card border border-border bg-surface">
                    <div className="border-b border-border px-3 py-2.5 text-xs font-medium text-foreground">历史会话</div>
                    <div className="max-h-[34rem] divide-y divide-border overflow-y-auto">
                      {sessions.length === 0 ? (
                        <div className="p-6 text-center text-xs text-muted">
                          {loadingSessions ? '正在读取…' : '点击“读取历史对话”查看该用户的会话'}
                        </div>
                      ) : sessions.map(session => (
                        <button
                          type="button"
                          key={session.id}
                          onClick={() => loadMessages(session)}
                          className={cn(
                            'w-full p-3 text-left transition-colors hover:bg-elevated/60',
                            selectedSessionId === session.id && 'bg-accent/10',
                          )}
                        >
                          <div className="line-clamp-2 text-xs font-medium text-foreground">{sessionTitle(session)}</div>
                          <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-muted">
                            <span>{session.message_count ?? 0} 条消息</span>
                            <span>{formatEpoch(session.last_active ?? session.started_at)}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-card border border-border bg-surface">
                    <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
                      <span className="truncate text-xs font-medium text-foreground">
                        {selectedSession ? sessionTitle(selectedSession) : '对话内容'}
                      </span>
                      <span className="text-[10px] text-muted">只显示用户问题与 AI 回复</span>
                    </div>
                    <div className="max-h-[34rem] space-y-3 overflow-y-auto p-4">
                      {loadingMessages ? (
                        <div className="py-10 text-center text-xs text-muted"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />读取中…</div>
                      ) : messages.length === 0 ? (
                        <div className="py-10 text-center text-xs text-muted">选择一个会话查看只读历史</div>
                      ) : messages.map((message, index) => (
                        <div
                          key={message.id || `${message.role}-${index}`}
                          className={cn(
                            'max-w-[92%] rounded-card px-3 py-2.5 text-sm leading-relaxed',
                            message.role === 'user'
                              ? 'ml-auto bg-accent/12 text-foreground'
                              : 'mr-auto border border-border bg-base text-secondary',
                          )}
                        >
                          <div className="mb-1 flex items-center gap-1.5 text-[10px] font-medium text-muted">
                            {message.role === 'user' ? <UserRound className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
                            {message.role === 'user' ? '用户' : 'AI'} · {formatEpoch(message.timestamp)}
                          </div>
                          <div className="whitespace-pre-wrap break-words">{message.content}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="grid min-h-[20rem] place-items-center rounded-card border border-border bg-surface text-sm text-muted">
                当前没有可查看的普通用户
              </div>
            )}
          </section>
        </div>

      </div>
    </>
  )
}
