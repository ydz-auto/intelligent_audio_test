/**
 * 全局 Agent 工作台魔法按钮（interfaces 层 components/layout；08_AI对话页.md §3.1B）。
 * AppHeader 右区全局控制区（INT-344 装配；落位次序置于全局算法切换器之前）。
 * 形态照 xagents_new_api `ai-discount-core`/`ai-discount-word` 实测 CSS
 * （web/src/styles/index.css:822-944 逐文件等价移植）：炫彩渐变 + 光斑旋转 + 星尘粒子流；
 * `prefers-reduced-motion` 关停由 CSS media 块承担。
 * 图标+文案换行修复（负责人 2026-10-17 反馈）：照 newAPI LocalSetupGuide 实测结构——
 * 图标与文案收进 `ai-discount-word` 内层 `inline-flex items-center justify-center gap-2` 容器，
 * 避免外层按钮无 flex 布局时 CJK 文本换行/失垂直居中。
 * RBAC（§5）：`report:read` 门槛同整页——device_admin 无 report:read 时整钮不渲染。
 */
import { Sparkles } from 'lucide-react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useAgentWorkbench } from '@/infrastructure/stores/agentWorkbenchStore'
import { cn } from '@/lib/utils'

export function AgentWorkbenchButton() {
  const { hasPermission } = usePermissions()
  const open = useAgentWorkbench((s) => s.open)
  const toggle = useAgentWorkbench((s) => s.toggle)
  const setOpen = useAgentWorkbench((s) => s.setOpen)

  // RBAC（§5）：device_admin 无 report:read 时魔法按钮与浮窗均不渲染
  if (!hasPermission('report:read')) return null

  const handleClick = () => {
    // 从整页形态回到登录壳任意页面：浮窗已关闭时重新打开
    if (!open) setOpen(true)
    else toggle()
  }

  return (
    <button
      aria-label='打开全局 Agent 工作台'
      className={cn(
        'ai-discount-core relative isolate h-9 shrink-0 cursor-pointer rounded-full border-0 px-4 font-bold text-white transition-all hover:brightness-110 active:translate-y-px focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
        open && 'ring-2 ring-primary/40'
      )}
      data-slot='button'
      onMouseEnter={() => {
        // TODO(INT-598)：hover 预加载浮窗内容（照 LocalSetupGuide preloadLocalSetupGuideContent 懒加载模式）
      }}
      onClick={handleClick}
      type='button'
    >
      {/* 内层 flex 容器照 newAPI LocalSetupGuide（local-setup-guide.tsx:110-118）：文案不换行、垂直居中 */}
      <span className='ai-discount-word inline-flex items-center justify-center gap-2'>
        <Sparkles aria-hidden='true' className='size-4' />
        <span className='hidden whitespace-nowrap sm:inline'>灵犀Agent</span>
        <span className='sr-only sm:hidden'>灵犀Agent</span>
      </span>
    </button>
  )
}
