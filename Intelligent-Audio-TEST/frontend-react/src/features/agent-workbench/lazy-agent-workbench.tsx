/**
 * Agent 工作台懒加载壳（interfaces 层，登录壳专用）：
 * 浮窗关闭时不加载 ai-chat / agent-providers 分块，登录壳任意页面首屏只带轻量开关判断；
 * 打开（含刷新后 persisted open=true）才动态拉取工作台本体。
 * 浮窗开关状态仍由 infrastructure/stores/agentWorkbenchStore 持有（跨页驻留语义不变）。
 */
import { lazy, Suspense } from 'react'

import { useAgentWorkbench } from '@/infrastructure/stores/agentWorkbenchStore'

const AgentWorkbenchWindow = lazy(() =>
  import('./agent-workbench').then((module) => ({
    default: module.AgentWorkbench,
  }))
)

export function LazyAgentWorkbench() {
  const open = useAgentWorkbench((state) => state.open)

  if (!open) return null

  return (
    <Suspense fallback={null}>
      <AgentWorkbenchWindow />
    </Suspense>
  )
}
