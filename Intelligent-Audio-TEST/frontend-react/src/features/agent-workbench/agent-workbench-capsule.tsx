/**
 * 最小化悬浮胶囊（interfaces 层 features/agent-workbench；08_AI对话页.md §3.1B）。
 * 浮窗最小化后收起为右下角悬浮胶囊，点击弹回（setMinimized(false)）。
 * 形态沿用魔法按钮炫彩渐变（ai-discount-core 类族，§3.1B 同一语言）。
 * 定位：.ai-discount-core 内置 position:relative 为无层自定义 CSS（src/styles/index.css:827），
 * 优先级高于 Tailwind 工具类，故用重要修饰 `fixed!` 确保胶囊固定右下角（P1-1 代码审计返修）。
 */
import { Sparkles } from 'lucide-react'

import { useAgentWorkbench } from '@/infrastructure/stores/agentWorkbenchStore'

export function AgentWorkbenchCapsule() {
  const setMinimized = useAgentWorkbench((s) => s.setMinimized)

  return (
    <button
      aria-label='恢复 Agent 工作台'
      className='ai-discount-core ai-discount-word fixed! right-4 bottom-4 z-50 flex size-12 shrink-0 cursor-pointer items-center justify-center rounded-full border-0 text-white shadow-2xl transition-all hover:brightness-110 active:translate-y-px focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none'
      data-slot='button'
      onClick={() => setMinimized(false)}
      type='button'
    >
      <Sparkles aria-hidden='true' className='size-5' />
    </button>
  )
}
