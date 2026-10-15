/**
 * 消息错误态（interfaces 层 ai-chat/message；08_AI对话页.md §3.4 照 newAPI message-error）：
 * Alert destructive「出错了」+ 描述 + 重试/编辑后重发/删除 操作组；「模型价格未配置」分支不引入（无计费业务）。
 */
import { AlertCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ERROR_MESSAGES } from '@/features/ai-chat/constants'

type MessageErrorProps = {
  onRetry?: () => void
  onEditPrompt?: () => void
  onDelete?: () => void
  disabled?: boolean
  errorCode?: string | null
}

export function MessageError({
  onRetry,
  onEditPrompt,
  onDelete,
  disabled,
  errorCode,
}: MessageErrorProps) {
  const isInterrupted = errorCode === 'interrupted'

  return (
    <Alert className='mt-1' variant='destructive'>
      <AlertCircle className='size-4' aria-hidden='true' />
      <AlertTitle>{ERROR_MESSAGES.title}</AlertTitle>
      <AlertDescription>
        {isInterrupted ? ERROR_MESSAGES.interrupted : ERROR_MESSAGES.generic}
        {!isInterrupted && (
          <p className='mt-0.5 text-xs'>{ERROR_MESSAGES.fallback}</p>
        )}
      </AlertDescription>
      <div className='mt-2 flex items-center gap-1.5'>
        {onRetry && (
          <Button
            className='h-7 px-2.5 text-xs'
            disabled={disabled}
            onClick={onRetry}
            size='sm'
            type='button'
          >
            重试
          </Button>
        )}
        {onEditPrompt && (
          <Button
            className='text-muted-foreground h-7 px-2.5 text-xs'
            disabled={disabled}
            onClick={onEditPrompt}
            size='sm'
            type='button'
            variant='ghost'
          >
            编辑后重发
          </Button>
        )}
        {onDelete && (
          <Button
            className='text-muted-foreground h-7 px-2.5 text-xs'
            disabled={disabled}
            onClick={onDelete}
            size='sm'
            type='button'
            variant='ghost'
          >
            删除
          </Button>
        )}
      </div>
    </Alert>
  )
}
