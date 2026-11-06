/**
 * 炫彩「连接你的 agent」入口按钮（interfaces 层 components/layout；INT-1153 二轮返工）。
 * 落点：灵犀Agent 页 /ai-chat 顶部条右上角 + 全局 Agent 工作台浮窗（小窗口）头行右上角；
 * 导航栏（顶栏 + 侧栏）不再保留该入口（负责人 2026-10-21 二轮裁定）。
 * 形态照 xagents_new_api `ai-discount-core`/`ai-discount-word`（index.css:826+）：
 * 与 AgentWorkbenchButton 同款炫彩魔法按钮；点击进入 /agent-connect 入口页
 * （INT-1140 负责人方案 2：入口按钮 = 炫彩，点击打开页面）。
 * compact 用于浮窗头行（空间紧凑，按钮按头行高度适配）。
 * RBAC：登录即可见（token 管理按当前用户本人，不需额外权限码）。
 */
import { Link } from '@tanstack/react-router'
import { Plug } from 'lucide-react'

import { cn } from '@/lib/utils'

export function AgentConnectButton({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      to='/agent-connect'
      aria-label='打开连接你的 agent'
      data-slot='button'
      className={cn(
        'ai-discount-core relative isolate inline-flex shrink-0 cursor-pointer items-center justify-center rounded-full border-0 text-white transition-all hover:brightness-110 active:translate-y-px focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
        compact ? 'h-7 px-2.5 text-xs font-semibold' : 'h-9 px-4 font-bold'
      )}
    >
      {/* 内层 flex 容器照 AgentWorkbenchButton（文案不换行、垂直居中） */}
      <span
        className={cn(
          'ai-discount-word inline-flex items-center justify-center',
          compact ? 'gap-1.5' : 'gap-2'
        )}
      >
        <Plug aria-hidden='true' className={compact ? 'size-3.5' : 'size-4'} />
        <span className='whitespace-nowrap'>连接你的 agent</span>
      </span>
    </Link>
  )
}
