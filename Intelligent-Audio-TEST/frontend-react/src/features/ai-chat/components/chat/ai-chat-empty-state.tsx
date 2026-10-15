/**
 * 空态四 starter（interfaces 层 ai-chat/chat；08_AI对话页.md §3.3 照 playground-empty-state 逐值）：
 * 图标位 + 标题「开始与 AI 助手对话」+ 描述 + starter 组；点击回填输入框不自动发送；
 * 按权限逐卡过滤（隐藏而非置灰）。
 */
import { MessagesSquare } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  EMPTY_STATE_COPY,
  STARTER_PROMPTS,
} from '@/features/ai-chat/constants'
import { useChatPermissions } from '@/application/ai-chat/useChatPermissions'

type AiChatEmptyStateProps = {
  onSelectPrompt: (prompt: string) => void
}

export function AiChatEmptyState({
  onSelectPrompt,
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
    <div className='flex min-h-[min(520px,calc(100svh-18rem))] items-center justify-center px-1 py-8 md:py-12'>
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

        <div className='grid gap-2 sm:grid-cols-2'>
          {visibleStarters.map(({ key, label, icon: Icon, prompt }) => (
            <Button
              className='h-auto min-h-11 justify-start gap-2 px-3 py-2.5 text-left whitespace-normal'
              key={key}
              onClick={() => onSelectPrompt(prompt)}
              variant='outline'
            >
              <Icon className='text-muted-foreground size-4' />
              <span>{label}</span>
            </Button>
          ))}
        </div>
      </div>
    </div>
  )
}
