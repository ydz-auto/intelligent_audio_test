/**
 * 对话记录目录（interfaces 层）：/ai-chat 左栏历史会话列表。
 * 数据来自服务端 GET /agent/sessions（按最近活跃倒序），点击切会话，
 * 「新对话」结束当前会话上下文。
 */
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAgentSessions } from '@/application/agent/use-agent-sessions'

type ConversationHistoryProps = {
  activeSessionId: string | null
  disabled?: boolean
  onSelect: (sessionId: string) => void
  onNew: () => void
}

function formatUpdatedAt(value: string | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  return sameDay
    ? date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString()
}

export function ConversationHistory({
  activeSessionId,
  disabled = false,
  onSelect,
  onNew,
}: ConversationHistoryProps) {
  const { data, isLoading } = useAgentSessions()
  const sessions = data ?? []

  return (
    <aside className='border-border/60 bg-muted/20 flex w-60 min-w-0 shrink-0 flex-col border-r'>
      <div className='flex shrink-0 items-center justify-between gap-2 px-3 py-3'>
        <span className='text-sm font-medium'>对话记录</span>
        <Button
          className='h-8 px-2'
          disabled={disabled}
          onClick={onNew}
          size='sm'
          type='button'
          variant='ghost'
        >
          <Plus className='size-4' />
          新对话
        </Button>
      </div>
      <div className='min-h-0 w-full min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-2 pb-3'>
        {isLoading && sessions.length === 0 ? (
          <p className='text-muted-foreground px-2 py-3 text-xs'>加载中…</p>
        ) : sessions.length === 0 ? (
          <p className='text-muted-foreground px-2 py-3 text-xs'>
            暂无对话记录，发一条消息即可开始。
          </p>
        ) : (
          <ul className='grid min-w-0 gap-1'>
            {sessions.map((session) => (
              <li className='min-w-0' key={session.id}>
                <button
                  className={cn(
                    'w-full min-w-0 cursor-pointer rounded-md px-2.5 py-2 text-left text-sm transition-colors',
                    session.id === activeSessionId
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
                  )}
                  disabled={disabled}
                  onClick={() => onSelect(session.id)}
                  title={session.title || '新对话'}
                  type='button'
                >
                  <span className='block truncate'>
                    {session.title || '新对话'}
                  </span>
                  <span className='text-muted-foreground/80 mt-0.5 block text-[11px]'>
                    {formatUpdatedAt(session.updatedAt)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
