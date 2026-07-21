import { useState, useEffect, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Save, Loader2, Check, Wifi, WifiOff, Eye, EyeOff, Shield,
  Shuffle, Plug, Zap, Settings2, ExternalLink, Trash2,
  Terminal, Copy, LogIn, LogOut,
} from 'lucide-react'
import { useSettings } from '@/lib/useSharedQueries'
import { api, type SettingsState } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

// 统一的输入框样式(与项目其他设置页一致)
const INPUT_CLS =
  'w-full h-9 px-2.5 rounded-lg bg-base border-0 ring-1 ring-border/30 text-xs font-mono text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30 transition-shadow'

const CODEX_PROVIDER = 'codex_cli'
const OPENAI_PROVIDER = 'openai_compat'
const XAI_PROVIDER = 'xai'
const CUSTOM_CODEX_MODEL = '__custom__'
const CODEX_COMMAND = 'codex'
const XAI_API_BASE = 'https://api.x.ai/v1'
const XAI_DEFAULT_MODEL = 'grok-4.5'

const CODEX_MODEL_OPTIONS = [
  { label: 'Codex 默认（推荐）', value: '', hint: '使用当前 Codex CLI 支持的默认模型' },
  { label: 'gpt-5.5', value: 'gpt-5.5', hint: '高能力模型' },
  { label: 'gpt-5', value: 'gpt-5', hint: '通用模型' },
]

const XAI_MODEL_OPTIONS = [
  { label: 'Grok 4.5（推荐）', value: 'grok-4.5', hint: 'SuperGrok 主力模型' },
  { label: 'Grok 4.5 Latest', value: 'grok-4.5-latest', hint: '跟踪最新 4.5 版本' },
  { label: 'Grok 4.20', value: 'grok-4.20', hint: '4.20 系列' },
  { label: 'Grok Code Fast', value: 'grok-code-fast', hint: '偏代码场景' },
  { label: '自定义…', value: '__custom__', hint: '填写其它 grok 模型 ID' },
]

type Preset = {
  label: string
  provider?: string
  url: string
  model: string
  codexCommand?: string
  website: string
  websiteLabel: string
  description: string
}

const PRESETS: Preset[] = [
  {
    label: 'Grok (xAI)',
    provider: XAI_PROVIDER,
    url: XAI_API_BASE,
    model: XAI_DEFAULT_MODEL,
    website: 'https://accounts.x.ai/',
    websiteLabel: 'accounts.x.ai',
    description: '使用 SuperGrok 订阅登录 xAI，或粘贴 xAI API Key。默认模型 Grok 4.5。',
  },
  {
    label: 'DeepSeek',
    url: 'https://api.deepseek.com',
    model: 'deepseek-chat',
    website: 'https://www.deepseek.com/',
    websiteLabel: 'deepseek.com',
    description: 'DeepSeek 官方 OpenAI 兼容接口。',
  },
  {
    label: '通义千问',
    url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-plus',
    website: 'https://tongyi.aliyun.com/',
    websiteLabel: 'tongyi.aliyun.com',
    description: '阿里云 DashScope 兼容模式接口。',
  },
  {
    label: '智谱 GLM',
    url: 'https://open.bigmodel.cn/api/paas/v4',
    model: 'glm-4',
    website: 'https://open.bigmodel.cn/',
    websiteLabel: 'open.bigmodel.cn',
    description: '智谱 AI 官方 OpenAI 兼容接口。',
  },
  {
    label: 'Kimi',
    url: 'https://api.moonshot.cn/v1',
    model: 'moonshot-v1-auto',
    website: 'https://platform.moonshot.cn/',
    websiteLabel: 'platform.moonshot.cn',
    description: '月之暗面 Moonshot 官方 OpenAI 兼容接口，支持超长上下文。',
  },
  {
    label: 'Codex CLI',
    provider: CODEX_PROVIDER,
    url: '',
    model: '',
    codexCommand: CODEX_COMMAND,
    website: 'https://developers.openai.com/codex/noninteractive',
    websiteLabel: 'codex exec',
    description: '调用本机 Codex CLI 的 codex exec, 适合已登录 ChatGPT/Codex 的本地环境。',
  },
]

export function SettingsAIPanel() {
  const qc = useQueryClient()
  const settings = useSettings()
  const s = settings.data

  const [provider, setProvider] = useState(OPENAI_PROVIDER)
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [codexCustomModel, setCodexCustomModel] = useState(false)
  const [xaiCustomModel, setXaiCustomModel] = useState(false)
  const [codexCommand, setCodexCommand] = useState(CODEX_COMMAND)
  const [customUa, setCustomUa] = useState(false)
  const [userAgent, setUserAgent] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)

  // xAI device login state
  const [xaiLoggingIn, setXaiLoggingIn] = useState(false)
  const [xaiLoginError, setXaiLoginError] = useState<string | null>(null)
  const [xaiDevice, setXaiDevice] = useState<{
    device_code: string
    user_code: string
    verification_uri: string
    verification_uri_complete?: string
    expires_in: number
    interval: number
  } | null>(null)
  const [copiedCode, setCopiedCode] = useState(false)
  const pollAbortRef = useRef(false)

  const isCodexProvider = provider === CODEX_PROVIDER
  const isXaiProvider = provider === XAI_PROVIDER
  const savedCodexProvider = s?.ai_provider === CODEX_PROVIDER
  const savedXaiProvider = s?.ai_provider === XAI_PROVIDER
  const xaiOauth = !!(s?.ai_xai?.has_oauth)
  const configured = s?.ai_configured ?? (
    savedCodexProvider
      ? !!(s?.ai_codex_command ?? CODEX_COMMAND)
      : savedXaiProvider
        ? (xaiOauth || !!s?.has_ai_key)
        : s?.has_ai_key
  )
  const selectedPreset = PRESETS.find(p =>
    (p.provider ?? OPENAI_PROVIDER) === provider &&
    (isCodexProvider
      ? p.codexCommand === codexCommand
      : isXaiProvider
        ? true
        : p.url === baseUrl),
  )
  const codexModelSelectValue = codexCustomModel ? CUSTOM_CODEX_MODEL : model
  const xaiModelSelectValue = xaiCustomModel || !XAI_MODEL_OPTIONS.some(o => o.value === model && o.value !== '__custom__')
    ? (xaiCustomModel ? '__custom__' : (XAI_MODEL_OPTIONS.some(o => o.value === model) ? model : '__custom__'))
    : model
  const canSave = isCodexProvider
    ? true
    : isXaiProvider
      ? !!model.trim()
      : !!baseUrl.trim() && !!model.trim()

  useEffect(() => {
    if (!s) return
    setProvider(s.ai_provider || OPENAI_PROVIDER)
    setBaseUrl(s.ai_base_url ?? '')
    setModel(s.ai_model ?? '')
    setCodexCustomModel(!!s.ai_model && !CODEX_MODEL_OPTIONS.some(o => o.value === s.ai_model))
    setXaiCustomModel(!!s.ai_model && !XAI_MODEL_OPTIONS.some(o => o.value === s.ai_model && o.value !== '__custom__'))
    setCodexCommand(s.ai_codex_command ?? CODEX_COMMAND)
    const ua = s.ai_user_agent ?? ''
    setCustomUa(!!ua)
    setUserAgent(ua)
  }, [s])

  useEffect(() => () => { pollAbortRef.current = true }, [])

  const save = useMutation({
    mutationFn: () => api.saveAiSettings({
      provider,
      base_url: isXaiProvider ? XAI_API_BASE : baseUrl,
      api_key: isCodexProvider ? '' : (apiKey || undefined),
      model,
      codex_command: isCodexProvider ? CODEX_COMMAND : codexCommand,
      user_agent: customUa ? userAgent : '',
    }),
    onSuccess: (result) => {
      qc.setQueryData(QK.settings, (prev: SettingsState | undefined) => prev ? {
        ...prev,
        ai_provider: result.ai_provider ?? provider,
        ai_base_url: isXaiProvider ? XAI_API_BASE : baseUrl,
        ai_model: result.ai_model ?? model,
        ai_codex_command: result.ai_codex_command ?? (isCodexProvider ? CODEX_COMMAND : codexCommand),
        ai_configured: result.ai_configured ?? (isCodexProvider || isXaiProvider ? true : (apiKey ? true : prev.ai_configured)),
        ai_user_agent: customUa ? userAgent : '',
        ai_xai: result.ai_xai ?? prev.ai_xai,
        has_ai_key: apiKey ? true : prev.has_ai_key,
        ai_api_key_masked: apiKey ? `${apiKey.slice(0, 4)}••••••${apiKey.slice(-4)}` : prev.ai_api_key_masked,
      } : prev)
      setApiKey('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      qc.invalidateQueries({ queryKey: QK.settings })
    },
  })

  const clear = useMutation({
    mutationFn: () => api.clearAiSettings(),
    onSuccess: () => {
      setProvider(OPENAI_PROVIDER)
      setBaseUrl('')
      setApiKey('')
      setModel('')
      setCodexCustomModel(false)
      setXaiCustomModel(false)
      setCodexCommand(CODEX_COMMAND)
      setXaiDevice(null)
      setXaiLoginError(null)
      qc.setQueryData(QK.settings, (prev: SettingsState | undefined) => prev ? {
        ...prev,
        ai_provider: OPENAI_PROVIDER,
        ai_base_url: '',
        ai_model: '',
        ai_codex_command: CODEX_COMMAND,
        ai_configured: false,
        has_ai_key: false,
        ai_api_key_masked: '',
        ai_xai: { auth_type: null, has_oauth: false, has_access_token: false, expires_at: null, expired: false },
      } : prev)
      setConfirmClear(false)
      qc.invalidateQueries({ queryKey: QK.settings })
    },
  })

  const applyPreset = (p: Preset) => {
    setProvider(p.provider ?? OPENAI_PROVIDER)
    setBaseUrl(p.url)
    setModel(p.model)
    setCodexCommand(p.codexCommand ?? CODEX_COMMAND)
    setCodexCustomModel(false)
    setXaiCustomModel(false)
    setTestResult(null)
    setXaiLoginError(null)
    if ((p.provider ?? OPENAI_PROVIDER) !== XAI_PROVIDER) {
      setXaiDevice(null)
      pollAbortRef.current = true
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await api.strategyAiTest()
      setTestResult({ ok: r.ok, msg: r.ok ? `连通成功 · ${r.model ?? provider}` : (r.error ?? '未知错误') })
    } catch (e: unknown) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : '测试失败' })
    } finally {
      setTesting(false)
    }
  }

  const startXaiLogin = async () => {
    pollAbortRef.current = false
    setXaiLoggingIn(true)
    setXaiLoginError(null)
    setXaiDevice(null)
    try {
      const device = await api.xaiDeviceStart()
      if (pollAbortRef.current) return
      setXaiDevice(device)
      setProvider(XAI_PROVIDER)
      setBaseUrl(XAI_API_BASE)
      if (!model) setModel(XAI_DEFAULT_MODEL)

      const url = device.verification_uri_complete || device.verification_uri
      try { window.open(url, '_blank', 'noopener,noreferrer') } catch { /* ignore */ }

      const deadline = Date.now() + (device.expires_in || 300) * 1000
      let intervalMs = Math.max((device.interval || 5) * 1000, 1000)
      let result: Awaited<ReturnType<typeof api.xaiDevicePoll>> | null = null

      while (Date.now() < deadline) {
        if (pollAbortRef.current) return
        await new Promise(r => setTimeout(r, intervalMs))
        if (pollAbortRef.current) return
        const poll = await api.xaiDevicePoll({
          device_code: device.device_code,
          model: model || XAI_DEFAULT_MODEL,
        })
        if (poll.status === 'authorized' || poll.ok) {
          result = poll
          break
        }
        if (poll.slow_down) intervalMs += 5000
      }

      if (!result) throw new Error('xAI 设备授权超时，请重试')
      if (pollAbortRef.current) return

      qc.setQueryData(QK.settings, (prev: SettingsState | undefined) => prev ? {
        ...prev,
        ai_provider: result!.ai_provider ?? XAI_PROVIDER,
        ai_base_url: XAI_API_BASE,
        ai_model: result!.ai_model ?? model ?? XAI_DEFAULT_MODEL,
        ai_configured: result!.ai_configured ?? true,
        ai_xai: result!.ai_xai ?? { auth_type: 'oauth', has_oauth: true, has_access_token: true },
        has_ai_key: false,
        ai_api_key_masked: '',
      } : prev)
      setProvider(XAI_PROVIDER)
      setBaseUrl(XAI_API_BASE)
      setModel(result.ai_model ?? model ?? XAI_DEFAULT_MODEL)
      setXaiDevice(null)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      qc.invalidateQueries({ queryKey: QK.settings })
    } catch (e: unknown) {
      if (!pollAbortRef.current) {
        setXaiLoginError(e instanceof Error ? e.message : 'xAI 登录失败')
      }
    } finally {
      setXaiLoggingIn(false)
    }
  }

  const cancelXaiLogin = () => {
    pollAbortRef.current = true
    setXaiLoggingIn(false)
    setXaiDevice(null)
    setXaiLoginError(null)
  }

  const logoutXai = async () => {
    try {
      await api.xaiLogout()
      qc.invalidateQueries({ queryKey: QK.settings })
    } catch { /* ignore */ }
  }

  const copyUserCode = async () => {
    if (!xaiDevice?.user_code) return
    try {
      await navigator.clipboard.writeText(xaiDevice.user_code)
      setCopiedCode(true)
      setTimeout(() => setCopiedCode(false), 1500)
    } catch { /* ignore */ }
  }

  const randomUa = () => {
    const chrome = 120 + Math.floor(Math.random() * 15)
    setUserAgent(
      `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chrome}.0.0.0 Safari/537.36`,
    )
  }

  const statusSubtitle = (() => {
    if (!configured) {
      if (isXaiProvider) return '使用 SuperGrok 登录或粘贴 xAI API Key 后即可调用 Grok。'
      if (isCodexProvider) return '使用本机 codex exec, 此处无需填写 API Key。'
      return '配置 API Key 后即可使用 AI 功能。'
    }
    if (savedCodexProvider) return `${s?.ai_codex_command ?? CODEX_COMMAND} · ${s?.ai_model || '默认模型'}`
    if (savedXaiProvider) {
      const auth = s?.ai_xai?.has_oauth ? 'SuperGrok OAuth' : (s?.ai_api_key_masked || 'API Key')
      return `${s?.ai_model || XAI_DEFAULT_MODEL} · ${auth}`
    }
    return `${s?.ai_model} · ${s?.ai_api_key_masked}`
  })()

  return (
    <div className="space-y-5 max-w-2xl">
      <Card icon={Plug} title="连接状态" right={
        configured && (
          <button onClick={handleTest} disabled={testing}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn bg-elevated hover:bg-elevated/80 text-xs text-secondary transition-colors duration-150 ease-smooth disabled:opacity-50">
            {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
            {testing ? '测试中' : '测试'}
          </button>
        )
      }>
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${configured ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-amber-500/10 text-amber-700 dark:text-amber-400'}`}>
            {configured ? <Wifi className="h-4.5 w-4.5" /> : <WifiOff className="h-4.5 w-4.5" />}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-foreground">{configured ? 'AI 已连接' : 'AI 未配置'}</div>
            <div className="text-xs text-muted mt-0.5 truncate">{statusSubtitle}</div>
          </div>
        </div>
        {testResult && (
          <div className={`mt-3 rounded-btn border px-3 py-2 text-xs ${testResult.ok ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'border-danger/30 bg-danger/10 text-danger'}`}>
            {testResult.msg}
          </div>
        )}
      </Card>

      <Card icon={Zap} title="快速预设">
        <div className="flex flex-wrap gap-2">
          {PRESETS.map(p => {
            const active = selectedPreset?.label === p.label
            return (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(p)}
                className={cn(
                  'inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-xs font-medium border transition-colors',
                  active
                    ? 'border-accent/40 bg-accent/10 text-accent'
                    : 'border-border bg-elevated/60 text-secondary hover:text-foreground hover:border-border',
                )}
              >
                {p.provider === CODEX_PROVIDER && <Terminal className="h-3 w-3" />}
                {p.provider === XAI_PROVIDER && <LogIn className="h-3 w-3" />}
                {p.label}
              </button>
            )
          })}
        </div>
        {selectedPreset && (
          <div className="mt-3 text-[11px] text-muted leading-relaxed">
            {selectedPreset.description}
            {' · '}
            <a href={selectedPreset.website} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent hover:underline">
              {selectedPreset.websiteLabel}
              <ExternalLink className="h-2.5 w-2.5" />
            </a>
          </div>
        )}
      </Card>

      {isXaiProvider && (
        <Card icon={LogIn} title="Grok / SuperGrok 登录">
          <div className="space-y-3">
            <p className="text-xs text-secondary leading-relaxed">
              参考 OpenCode 的 xAI 接入：使用官方 Grok-CLI OAuth 设备码登录。
              用你的 SuperGrok 订阅在浏览器完成授权后，本机保存 access/refresh token，并默认使用
              <span className="font-mono text-foreground"> {XAI_DEFAULT_MODEL} </span>
              调用 <span className="font-mono">api.x.ai</span>。
            </p>

            {xaiOauth && !xaiLoggingIn && (
              <div className="flex items-center justify-between gap-3 rounded-btn border border-emerald-500/25 bg-emerald-500/10 px-3 py-2">
                <div className="text-xs text-emerald-800 dark:text-emerald-300">
                  已通过 SuperGrok OAuth 登录
                  {s?.ai_xai?.expires_at ? (
                    <span className="text-muted ml-1">
                      · token 约 {new Date((s.ai_xai.expires_at || 0) * 1000).toLocaleString()} 前有效
                    </span>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={logoutXai}
                  className="inline-flex items-center gap-1 h-7 px-2.5 rounded-btn text-[11px] text-secondary hover:text-foreground bg-surface border border-border"
                >
                  <LogOut className="h-3 w-3" />
                  退出登录
                </button>
              </div>
            )}

            {xaiDevice && (
              <div className="rounded-btn border border-border bg-elevated/50 p-3 space-y-2">
                <div className="text-[11px] text-muted">在浏览器打开 xAI 授权页，输入下方代码：</div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 h-10 px-3 rounded-lg bg-base ring-1 ring-border/40 font-mono text-lg tracking-[0.25em] font-semibold text-foreground flex items-center">
                    {xaiDevice.user_code}
                  </code>
                  <button type="button" onClick={copyUserCode}
                    className="h-10 px-3 rounded-lg border border-border bg-surface text-xs text-secondary hover:text-foreground inline-flex items-center gap-1">
                    {copiedCode ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedCode ? '已复制' : '复制'}
                  </button>
                </div>
                <a
                  href={xaiDevice.verification_uri_complete || xaiDevice.verification_uri}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
                >
                  打开 {xaiDevice.verification_uri}
                  <ExternalLink className="h-3 w-3" />
                </a>
                <div className="text-[11px] text-muted inline-flex items-center gap-1.5">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  等待浏览器授权完成…
                </div>
              </div>
            )}

            {xaiLoginError && (
              <div className="rounded-btn border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                {xaiLoginError}
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {!xaiLoggingIn ? (
                <button
                  type="button"
                  onClick={startXaiLogin}
                  className="inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-foreground text-base text-sm font-semibold hover:opacity-90 transition-opacity"
                >
                  <LogIn className="h-3.5 w-3.5" />
                  {xaiOauth ? '重新登录 SuperGrok' : '登录 SuperGrok'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={cancelXaiLogin}
                  className="inline-flex items-center gap-1.5 h-9 px-4 rounded-xl border border-border bg-elevated text-sm text-secondary hover:text-foreground"
                >
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  取消等待
                </button>
              )}
            </div>

            <div className="text-[11px] text-muted">
              也可以不走 OAuth，在下方直接粘贴 xAI Console 的 API Key（同样走 api.x.ai）。
            </div>
          </div>
        </Card>
      )}

      <Card
        icon={Settings2}
        title="自定义配置"
        right={<span className="text-[10px] text-muted font-mono px-2 py-0.5 rounded-full bg-elevated border border-border">Chat Completions 接口</span>}
      >
        <div className="space-y-3">
          {isCodexProvider ? (
            <>
              <Field label="命令" hint="固定使用本机 PATH 中的 codex">
                <input type="text" value={CODEX_COMMAND} readOnly className={INPUT_CLS + ' opacity-80'} />
              </Field>
              <Field
                label="模型"
                hint={codexCustomModel
                  ? '填写 Codex CLI 支持的模型 ID'
                  : CODEX_MODEL_OPTIONS.find(o => o.value === model)?.hint}
              >
                <select
                  value={codexModelSelectValue}
                  onChange={e => {
                    const value = e.target.value
                    if (value === CUSTOM_CODEX_MODEL) {
                      setCodexCustomModel(true)
                      if (CODEX_MODEL_OPTIONS.some(o => o.value === model)) setModel('')
                    } else {
                      setCodexCustomModel(false)
                      setModel(value)
                    }
                  }}
                  className={INPUT_CLS}
                >
                  {CODEX_MODEL_OPTIONS.map(option => (
                    <option key={option.label} value={option.value}>{option.label}</option>
                  ))}
                  <option value={CUSTOM_CODEX_MODEL}>自定义模型</option>
                </select>
                {codexCustomModel && (
                  <input
                    type="text"
                    value={model}
                    onChange={e => setModel(e.target.value)}
                    placeholder="gpt-5.5"
                    className={INPUT_CLS + ' mt-2'}
                  />
                )}
              </Field>
            </>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="API 地址">
                  <input
                    type="text"
                    value={isXaiProvider ? XAI_API_BASE : baseUrl}
                    onChange={e => setBaseUrl(e.target.value)}
                    readOnly={isXaiProvider}
                    placeholder="https://api.deepseek.com"
                    className={cn(INPUT_CLS, isXaiProvider && 'opacity-80')}
                  />
                </Field>
                <Field label="模型" hint={isXaiProvider ? 'SuperGrok 推荐 grok-4.5' : undefined}>
                  {isXaiProvider ? (
                    <>
                      <select
                        value={xaiModelSelectValue}
                        onChange={e => {
                          const value = e.target.value
                          if (value === '__custom__') {
                            setXaiCustomModel(true)
                            if (XAI_MODEL_OPTIONS.some(o => o.value === model && o.value !== '__custom__')) setModel('')
                          } else {
                            setXaiCustomModel(false)
                            setModel(value)
                          }
                        }}
                        className={INPUT_CLS}
                      >
                        {XAI_MODEL_OPTIONS.map(option => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                      {(xaiCustomModel || xaiModelSelectValue === '__custom__') && (
                        <input
                          type="text"
                          value={model}
                          onChange={e => setModel(e.target.value)}
                          placeholder="grok-4.5"
                          className={INPUT_CLS + ' mt-2'}
                        />
                      )}
                    </>
                  ) : (
                    <input type="text" value={model} onChange={e => setModel(e.target.value)} placeholder="deepseek-chat" className={INPUT_CLS} />
                  )}
                </Field>
              </div>

              <Field label={isXaiProvider ? 'API KEY（可选，OAuth 已登录时可留空）' : 'API KEY'}>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type={showKey ? 'text' : 'password'}
                      value={apiKey}
                      onChange={e => setApiKey(e.target.value)}
                      placeholder={s?.has_ai_key && !isXaiProvider ? '已配置，留空则保持不变' : (isXaiProvider && xaiOauth ? '已 OAuth 登录，可留空' : 'sk-...')}
                      className={INPUT_CLS + ' pr-9'}
                    />
                    <button type="button" onClick={() => setShowKey(v => !v)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-foreground">
                      {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  <button type="button" onClick={handleTest} disabled={testing || (!configured && !apiKey && !(isXaiProvider && xaiOauth))}
                    className="h-9 px-3 rounded-lg border border-border bg-elevated text-xs text-secondary hover:text-foreground disabled:opacity-40 inline-flex items-center gap-1.5 shrink-0">
                    {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wifi className="h-3.5 w-3.5" />}
                    测试
                  </button>
                </div>
              </Field>
            </>
          )}

          <div className="pt-1 border-t border-border/60">
            <div className="flex items-center justify-between py-2">
              <span className="text-xs text-secondary">自定义 USER-AGENT</span>
              <button
                type="button"
                onClick={() => {
                  const next = !customUa
                  setCustomUa(next)
                  if (next && !userAgent) randomUa()
                }}
                className={cn(
                  'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                  customUa ? 'bg-accent' : 'bg-elevated ring-1 ring-border',
                )}
              >
                <span className={cn('inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform', customUa ? 'translate-x-[18px]' : 'translate-x-0.5')} />
              </button>
            </div>
            {customUa && (
              <div className="flex gap-2">
                <input type="text" value={userAgent} onChange={e => setUserAgent(e.target.value)} className={INPUT_CLS} />
                <button type="button" onClick={randomUa}
                  className="h-9 px-3 rounded-lg border border-border bg-elevated text-xs text-secondary hover:text-foreground inline-flex items-center gap-1 shrink-0">
                  <Shuffle className="h-3.5 w-3.5" />
                  随机
                </button>
              </div>
            )}
          </div>
        </div>
      </Card>

      <div className="rounded-card border border-amber-500/25 bg-amber-500/10 px-4 py-3 flex items-start gap-2 text-xs text-amber-800 dark:text-amber-300">
        <Shield className="h-4 w-4 shrink-0 mt-0.5" />
        <span>API Key / OAuth Token 仅保存在本机项目文件中，不会上传到任何服务器。请妥善保管。</span>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending || !canSave}
          className="flex-1 h-10 rounded-xl bg-accent text-white text-sm font-semibold flex items-center justify-center gap-2 hover:bg-accent/90 disabled:opacity-40 transition-all"
        >
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
          {saved ? '已保存' : '保存配置'}
        </button>
        {configured && (
          <button
            type="button"
            onClick={() => setConfirmClear(true)}
            className="h-10 px-3 rounded-xl border border-border text-secondary hover:text-danger hover:border-danger/40 transition-colors"
            title="清空 AI 配置"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {confirmClear && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setConfirmClear(false)} />
          <div className="relative w-full max-w-sm rounded-card border border-border bg-surface p-5 shadow-xl space-y-4">
            <div className="text-sm font-medium text-foreground">清空 AI 配置？</div>
            <div className="text-xs text-muted">将删除本机保存的 API Key、Grok OAuth 会话与模型设置。自定义 User-Agent 会保留。</div>
            <div className="flex gap-2">
              <button type="button" onClick={() => setConfirmClear(false)} className="flex-1 h-9 rounded-lg border border-border text-xs text-secondary">取消</button>
              <button type="button" onClick={() => clear.mutate()} disabled={clear.isPending}
                className="flex-1 h-9 rounded-lg bg-danger text-white text-xs font-medium disabled:opacity-50">
                {clear.isPending ? '清除中…' : '确认清空'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Card({ icon: Icon, title, right, children }: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  right?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-medium text-foreground">{title}</h3>
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-medium text-secondary">{label}</span>
        {hint && <span className="text-[10px] text-muted truncate">{hint}</span>}
      </div>
      {children}
    </label>
  )
}
