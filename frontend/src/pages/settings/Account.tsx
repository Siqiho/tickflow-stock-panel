import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { KeyRound, Loader2, LogOut, ShieldCheck, UserRound } from 'lucide-react'
import { api } from '@/lib/api'
import { clearAccountLocalState } from '@/lib/accountLocalState'

const MIN_PASSWORD_LENGTH = 6

export function SettingsAccountPanel() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const account = useQuery({ queryKey: ['auth', 'status'], queryFn: api.authStatus })
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [message, setMessage] = useState('')

  const logout = useMutation({
    mutationFn: api.authLogout,
    onSuccess: () => {
      clearAccountLocalState()
      queryClient.clear()
      window.location.assign('/login')
    },
  })
  const changePassword = useMutation({
    mutationFn: () => api.authChangePassword(oldPassword, newPassword),
    onSuccess: () => {
      setMessage('密码已修改，请重新登录')
      setTimeout(() => window.location.assign('/login'), 700)
    },
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setMessage('')
    if (newPassword.length < MIN_PASSWORD_LENGTH) { setMessage(`新密码至少 ${MIN_PASSWORD_LENGTH} 位`); return }
    if (newPassword !== confirmPassword) { setMessage('两次新密码不一致'); return }
    changePassword.mutate()
  }

  const user = account.data?.user
  const quota = account.data?.ai_quota
  const isSignedIn = account.data?.authenticated === true && !!user
  const isPasswordlessLocalOwner = account.data?.configured === false
  const accountName = account.isLoading
    ? '加载中…'
    : account.isError
      ? '账号信息加载失败'
      : isPasswordlessLocalOwner
        ? '本地管理员'
        : user?.username || '未登录'
  const accountRole = account.isLoading
    ? '正在读取账号状态'
    : account.isError
      ? String((account.error as Error)?.message || '请稍后重试')
      : isPasswordlessLocalOwner
        ? '尚未设置访问密码'
        : user?.role === 'admin'
          ? '服务器管理员'
          : user?.role === 'user'
            ? '独立用户空间'
            : '当前没有有效登录会话'

  return (
    <div className="max-w-2xl space-y-4">
      <section className="rounded-card border border-border bg-surface p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/10 text-accent">
              <UserRound className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">{accountName}</h2>
              <div className="mt-0.5 flex items-center gap-1 text-xs text-muted">
                <ShieldCheck className="h-3 w-3" />
                {accountRole}
              </div>
            </div>
          </div>
          {isSignedIn && (
            <button
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              className="inline-flex h-9 items-center gap-1.5 rounded-btn border border-border px-3 text-xs text-secondary hover:text-danger disabled:opacity-50"
            >
              {logout.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
              退出登录
            </button>
          )}
        </div>
        {quota && user?.role !== 'admin' && (
          <div className="mt-4 rounded-btn bg-elevated px-3 py-2.5 text-xs text-secondary">
            今日共享 AI 额度：已用 {quota.used} / {quota.limit}，剩余 {quota.remaining}
          </div>
        )}
      </section>

      {isPasswordlessLocalOwner ? (
        <section className="rounded-card border border-border bg-surface p-5">
          <div className="mb-2 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-foreground">设置访问密码</h2>
          </div>
          <p className="text-xs leading-relaxed text-muted">
            当前仅允许本机或内网以兼容管理员身份访问。设置密码后，账号会正式初始化并要求登录。
          </p>
          <button
            type="button"
            onClick={() => navigate('/login?redirect=/settings', { replace: false })}
            className="mt-4 inline-flex h-9 items-center rounded-btn bg-accent px-4 text-xs font-medium text-white hover:bg-accent/90"
          >
            前往设置访问密码
          </button>
        </section>
      ) : isSignedIn ? (
        <section className="rounded-card border border-border bg-surface p-5">
          <div className="mb-4 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-foreground">修改密码</h2>
          </div>
          <form onSubmit={submit} className="space-y-3">
            <input type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)} placeholder="当前密码" autoComplete="current-password" className="h-10 w-full rounded-input border border-border bg-base px-3 text-sm outline-none focus:border-accent/50" />
            <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder={`新密码（至少 ${MIN_PASSWORD_LENGTH} 位）`} autoComplete="new-password" className="h-10 w-full rounded-input border border-border bg-base px-3 text-sm outline-none focus:border-accent/50" />
            <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder="再次输入新密码" autoComplete="new-password" className="h-10 w-full rounded-input border border-border bg-base px-3 text-sm outline-none focus:border-accent/50" />
            {(message || changePassword.error) && <div className="text-xs text-danger">{message || String((changePassword.error as Error).message)}</div>}
            <button type="submit" disabled={changePassword.isPending || !oldPassword || !newPassword} className="inline-flex h-9 items-center gap-1.5 rounded-btn bg-accent px-4 text-xs font-medium text-white disabled:opacity-50">
              {changePassword.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              保存新密码
            </button>
          </form>
        </section>
      ) : null}
    </div>
  )
}
