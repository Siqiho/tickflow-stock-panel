import type { FrontendSlotContextMap, FrontendSlotName } from './types'
import { getFrontendSlotRegistrations } from './registry'
import { ExtensionBoundary } from './ExtensionBoundary'

type Props<K extends FrontendSlotName> = {
  name: K
  context: FrontendSlotContextMap[K]
  compact?: boolean
}

export function ExtensionSlot<K extends FrontendSlotName>({ name, context, compact }: Props<K>) {
  let registrations: ReturnType<typeof getFrontendSlotRegistrations<K>> = []
  try {
    registrations = getFrontendSlotRegistrations(name)
  } catch {
    // 扩展注册表尚未冻结（HMR / 首屏竞态）时，工具栏插槽先空渲染，避免整页炸掉。
    return null
  }
  if (registrations.length === 0) return null
  return registrations.map(registration => {
    const SlotComponent = registration.component
    return (
      <ExtensionBoundary
        key={`${registration.extensionId}:${registration.id}`}
        extensionId={registration.extensionId}
        compact={compact}
      >
        <SlotComponent {...context} />
      </ExtensionBoundary>
    )
  })
}
