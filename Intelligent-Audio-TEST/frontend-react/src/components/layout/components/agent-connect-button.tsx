/**
 * 全局「联接你的 agent」入口按钮（interfaces 层 components/layout；INT-1153）。
 * AppHeader 右区全局控制区（落位次序：灵犀Agent 魔法按钮之后、算法切换器之前）。
 * 形态照 xagents_new_api `ai-discount-core`/`ai-discount-word`（index.css:826+）：
 * 与 AgentWorkbenchButton 同款炫彩魔法按钮；点击进入 /agent-connect 入口页
 * （INT-1140 负责人方案 2：入口按钮 = 炫彩，点击打开页面）。
 * RBAC：登录即可见（token 管理按当前用户本人，不需额外权限码）。
 */
import { Link } from '@tanstack/react-router'
import { Sparkles } from 'lucide-react'

import { cn } from '@/lib/utils'

export function AgentConnectButton() {
  return (
    <Link
      to='/agent-connect'
      aria-label='打开联接你的 agent'
      className={cn(
        'ai-discount-core relative isolate h-9 shrink-0 cursor-pointer rounded-full border-0 px-4 font-bold text-white transition-all hover:brightness-110 active:translate-y-px focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none'
      )}
    >
      {/* 内层 flex 容器照 AgentWorkbenchButton（文案不换行、垂直居中） */}
      <span className='ai-discount-word inline-flex items-center justify-center gap-2'>
        <Sparkles aria-hidden='true' className='size-4' />
        <span className='hidden whitespace-nowrap sm:inline'>联接你的 agent</span>
        <span className='sr-only sm:hidden'>联接你的 agent</span>
      </span>
    </Link>
  )
}
