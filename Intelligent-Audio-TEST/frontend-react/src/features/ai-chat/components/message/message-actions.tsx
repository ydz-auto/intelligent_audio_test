/**
 * 消息操作组（interfaces 层 ai-chat/message；08_AI对话页.md §3.4 照 newAPI message-actions）：
 * 复制 / 显示源码·预览 / 重新生成 / 编辑 / 删除 / 撤销修改（带文档变更时）；
 * 桌面 hover 显（最后一条 assistant 恒显），生成中禁用；移动端收 MoreHorizontal 菜单。
 */
import {
  Check,
  Copy,
  Edit,
  FileCode2,
  MoreHorizontal,
  RefreshCw,
  Trash2,
  Undo2,
} from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import { getCurrentMessageContent } from '@/features/ai-chat/lib/message'

import type { ChatMessage } from '@/domain/models/aiChat'

type MessageActionsProps = {
  message: ChatMessage
  onRegenerate?: (message: ChatMessage) => void
  onEdit?: (message: ChatMessage) => void
  onDelete?: (message: ChatMessage) => void
  onUndo?: (message: ChatMessage) => void
  onToggleSource?: (message: ChatMessage) => void
  isSourceVisible?: boolean
  isGenerating?: boolean
  alwaysVisible?: boolean
  className?: string
}

export function MessageActions({
  message,
  onRegenerate,
  onEdit,
  onDelete,
  onUndo,
  onToggleSource,
  isSourceVisible,
  isGenerating,
  alwaysVisible,
}: MessageActionsProps) {
  const isMobile = useIsMobile()
  const [copied, setCopied] = useState(false)
  const content = getCurrentMessageContent(message)
  const hasContent = content.length > 0
  const hasDocumentChange = (message.documentChanges?.length ?? 0) > 0

  const handleCopy = async () => {
    if (!hasContent) {
      toast.info('没有可复制的内容')
      return
    }
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      toast.success('已复制')
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('复制失败')
    }
  }

  const handleAction = (action: () => void) => {
    if (isGenerating) {
      toast.info('请等待当前回复生成完成')
      return
    }
    action()
  }

  const actionClass = cn(
    'text-muted-foreground hover:text-foreground size-7 hover:bg-muted/70',
    'disabled:pointer-events-none disabled:opacity-40'
  )

  const desktopActions = (
    <div
      className={cn(
        'hidden items-center gap-0.5 md:flex',
        alwaysVisible ? 'opacity-100' : 'opacity-0 transition-opacity group-hover:opacity-100'
      )}
    >
      <Button
        aria-label='复制'
        className={actionClass}
        disabled={isGenerating}
        onClick={handleCopy}
        size='icon'
        type='button'
        variant='ghost'
      >
        {copied ? (
          <Check className='text-success size-4' />
        ) : (
          <Copy className='size-4' />
        )}
      </Button>
      {hasContent && (
        <Button
          aria-label={isSourceVisible ? '显示预览' : '显示源码'}
          className={actionClass}
          disabled={isGenerating}
          onClick={() => onToggleSource?.(message)}
          size='icon'
          type='button'
          variant='ghost'
        >
          <FileCode2 className='size-4' />
        </Button>
      )}
      {hasDocumentChange && (
        <Button
          aria-label='撤销修改'
          className={actionClass}
          disabled={isGenerating}
          onClick={() => handleAction(() => onUndo?.(message))}
          size='icon'
          type='button'
          variant='ghost'
        >
          <Undo2 className='size-4' />
        </Button>
      )}
      {onRegenerate && (
        <Button
          aria-label='重新生成'
          className={actionClass}
          disabled={isGenerating}
          onClick={() => handleAction(() => onRegenerate(message))}
          size='icon'
          type='button'
          variant='ghost'
        >
          <RefreshCw className='size-4' />
        </Button>
      )}
      {onEdit && (
        <Button
          aria-label='编辑'
          className={actionClass}
          disabled={isGenerating}
          onClick={() => handleAction(() => onEdit(message))}
          size='icon'
          type='button'
          variant='ghost'
        >
          <Edit className='size-4' />
        </Button>
      )}
      {onDelete && (
        <Button
          aria-label='删除'
          className={cn(actionClass, 'hover:text-destructive hover:bg-destructive/10')}
          disabled={isGenerating}
          onClick={() => handleAction(() => onDelete(message))}
          size='icon'
          type='button'
          variant='ghost'
        >
          <Trash2 className='size-4' />
        </Button>
      )}
    </div>
  )

  if (isMobile) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              aria-label='打开菜单'
              className={cn(actionClass, 'flex md:hidden')}
              size='icon'
              type='button'
              variant='ghost'
            >
              <MoreHorizontal className='size-4' />
            </Button>
          }
        />
        <DropdownMenuContent align='start' className='min-w-40'>
          <DropdownMenuItem className='min-h-11' onClick={handleCopy}>
            <Copy className='mr-2 size-4' />
            复制
          </DropdownMenuItem>
          {hasDocumentChange && (
            <DropdownMenuItem
              className='min-h-11'
              onClick={() => handleAction(() => onUndo?.(message))}
            >
              <Undo2 className='mr-2 size-4' />
              撤销修改
            </DropdownMenuItem>
          )}
          {onRegenerate && (
            <DropdownMenuItem
              className='min-h-11'
              onClick={() => handleAction(() => onRegenerate(message))}
            >
              <RefreshCw className='mr-2 size-4' />
              重新生成
            </DropdownMenuItem>
          )}
          {onEdit && (
            <DropdownMenuItem
              className='min-h-11'
              onClick={() => handleAction(() => onEdit(message))}
            >
              <Edit className='mr-2 size-4' />
              编辑
            </DropdownMenuItem>
          )}
          {onDelete && (
            <DropdownMenuItem
              className='text-destructive min-h-11'
              onClick={() => handleAction(() => onDelete(message))}
            >
              <Trash2 className='mr-2 size-4' />
              删除
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }

  return desktopActions
}
