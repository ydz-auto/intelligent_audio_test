/**
 * 空态（interfaces 层 ai-chat/chat；08_AI对话页.md §3.3 照 playground-empty-state 逐值）：
 * 图标位 + 标题「开始与灵犀Agent对话」+ 描述（含 Demo 说明尾注 §3.10 落点③）+
 * **全能力入口/分组**——区一「常用入门」（报告高频四卡，Report First 口径）+ 区二「全能力分组」
 * （11 域入口卡，2026-10-17 08:06 负责人口径：灵犀Agent 主工作台主推全部能力、不只报告三件）；
 * 点击回填输入框不自动发送；按权限逐卡过滤（常用四卡隐藏而非置灰；分组卡在册权限码命中即显可执行，
 * 无码/无权限域统一标「待接入」、可显不可执行——红线：不假接线）。
 */
import { MessagesSquare } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  CAPABILITY_GROUPS,
  EMPTY_STATE_COPY,
  STARTER_PROMPTS,
} from '@/features/ai-chat/constants'
import { useChatPermissions } from '@/application/ai-chat/useChatPermissions'

type AiChatEmptyStateProps = {
  /** 点击 starter 只回填输入框并聚焦，不自动发送（§3.3） */
  onFillPrompt: (prompt: string) => void
  /** 全局 Agent 工作台浮窗紧凑形态（§3.1B） */
  compact?: boolean
}

export function AiChatEmptyState({
  onFillPrompt,
  compact = false,
}: AiChatEmptyStateProps) {
  const permissions = useChatPermissions()
  const permissionChecks: Record<string, boolean> = {
    'report:create': permissions.canGenerate,
    'report:compare': permissions.canCompare,
    'report:read': permissions.canRead,
  }

  const visibleStarters = STARTER_PROMPTS.filter(
    (starter) =>
      starter.requiredPermission === null ||
      permissionChecks[starter.requiredPermission] === true
  )

  return (
    <div
      className={
        compact
          ? 'flex min-h-[min(320px,calc(100svh-22rem))] items-center justify-center px-1 py-4'
          : 'flex min-h-[min(520px,calc(100svh-18rem))] items-center justify-center px-1 py-8 md:py-12'
      }
    >
      <div className='grid w-full max-w-2xl gap-5 text-center'>
        <div className='bg-muted/50 text-muted-foreground mx-auto flex size-11 items-center justify-center rounded-xl border'>
          <MessagesSquare className='size-5' aria-hidden='true' />
        </div>

        <div className='grid gap-2'>
          <h2 className='text-balance text-xl font-semibold tracking-tight md:text-2xl'>
            {EMPTY_STATE_COPY.title}
          </h2>
          <p className='text-muted-foreground mx-auto max-w-lg text-sm leading-6 text-balance'>
            {EMPTY_STATE_COPY.description}
          </p>
        </div>

        {visibleStarters.length > 0 && (
          <section className='grid gap-2 text-left'>
            <h3 className='text-muted-foreground text-xs font-semibold tracking-wide'>
              {EMPTY_STATE_COPY.commonStartersTitle}
            </h3>
            <div className='grid gap-2 sm:grid-cols-2'>
              {visibleStarters.map(({ key, label, icon: Icon, prompt }) => (
                <Button
                  className='h-auto min-h-11 justify-start gap-2 px-3 py-2.5 text-left whitespace-normal'
                  key={key}
                  onClick={() => onFillPrompt(prompt)}
                  variant='outline'
                >
                  <Icon className='text-muted-foreground size-4' />
                  <span>{label}</span>
                </Button>
              ))}
            </div>
          </section>
        )}

        <section className='grid gap-2 text-left'>
          <h3 className='text-muted-foreground text-xs font-semibold tracking-wide'>
            {EMPTY_STATE_COPY.capabilityGroupsTitle}
          </h3>
          <div className='grid gap-2 sm:grid-cols-2'>
            {CAPABILITY_GROUPS.map((group) => {
              const executable =
                group.requiredPermission !== null &&
                permissions.hasPermission(group.requiredPermission)
              const labelText =
                group.domainLabel !== group.label
                  ? `${group.label}（${group.domainLabel}）`
                  : group.label
              return (
                <div
                  className={cn(
                    'rounded-lg border p-3 text-left transition-colors',
                    executable
                      ? 'border-border bg-background'
                      : 'border-border/60 bg-muted/20'
                  )}
                  key={group.key}
                >
                  <div className='flex items-center gap-2'>
                    <group.icon
                      className='text-muted-foreground size-4 shrink-0'
                      aria-hidden='true'
                    />
                    <span className='text-sm leading-tight font-medium'>
                      {labelText}
                    </span>
                    {group.toolCount !== null && (
                      <Badge
                        className='text-muted-foreground ms-auto shrink-0'
                        variant='outline'
                      >
                        {group.toolCount} 工具
                      </Badge>
                    )}
                  </div>
                  {executable && group.prompt ? (
                    <button
                      className='text-muted-foreground hover:text-foreground hover:bg-accent mt-2 flex h-6 w-full cursor-pointer items-center gap-1 rounded-md border px-2 text-xs transition-colors'
                      onClick={() => onFillPrompt(group.prompt!)}
                      type='button'
                    >
                      {group.prompt}
                    </button>
                  ) : (
                    <span className='text-muted-foreground/80 mt-2 flex h-6 w-full items-center gap-1 rounded-md border border-dashed px-2 text-xs'>
                      {group.prompt ?? '待后端立项'}
                      <Badge className='ms-auto shrink-0' variant='warning'>
                        {EMPTY_STATE_COPY.capabilityPendingBadge}
                      </Badge>
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      </div>
    </div>
  )
}
