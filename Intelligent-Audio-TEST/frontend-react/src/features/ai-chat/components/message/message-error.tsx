/**
 * 消息错误态（interfaces 层 ai-chat/message；08_AI对话页.md §3.4 照 newAPI message-error）：
 * Alert destructive「出错了」+ 描述 + 重试/编辑后重发/删除 操作组；「模型价格未配置」分支不引入（无计费业务）。
 */
import { AlertCircle } from 'lucide-react'
import { Link } from '@tanstack/react-router'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  AGENT_PROVIDER_NOT_CONFIGURED_CODE,
} from '@/domain/models/agentProvider'
import { ERROR_MESSAGES } from '@/features/ai-chat/constants'
import {
  AGENT_PROVIDERS_COPY,
  AGENT_PROVIDERS_ROUTE,
  AGENT_PROVIDER_MANAGE_PERMISSION,
} from '@/features/agent-providers/constants'

type MessageErrorProps = {
  onRetry?: () => void
  onEditPrompt?: () => void
  onDelete?: () => void
  disabled?: boolean
  errorCode?: string | null
  /** 语义化错误详情（use-chat-handler fail() 落的内容：无供应商/无模型/网络失败等） */
  detail?: string
}

export function MessageError({
  onRetry,
  onEditPrompt,
  onDelete,
  disabled,
  errorCode,
  detail,
}: MessageErrorProps) {
  const { hasPermission } = usePermissions()
  const isInterrupted = errorCode === 'interrupted'
  const providerMissing = errorCode === AGENT_PROVIDER_NOT_CONFIGURED_CODE
  const canManageProvider = hasPermission(AGENT_PROVIDER_MANAGE_PERMISSION)

  return (
    <Alert className='mt-1' variant='destructive'>
      <AlertCircle className='size-4' aria-hidden='true' />
      <AlertTitle>
        {providerMissing ? AGENT_PROVIDERS_COPY.guidanceTitle : ERROR_MESSAGES.title}
      </AlertTitle>
      <AlertDescription>
        {isInterrupted ? (
          ERROR_MESSAGES.interrupted
        ) : providerMissing ? (
          <p>{AGENT_PROVIDERS_COPY.guidanceDescription}</p>
        ) : (
          <>
            <p>{detail?.trim() ? detail.trim() : ERROR_MESSAGES.generic}</p>
            <p className='mt-0.5 text-xs'>{ERROR_MESSAGES.fallback}</p>
          </>
        )}
      </AlertDescription>
      <div className='mt-2 flex items-center gap-1.5'>
        {providerMissing && canManageProvider && (
          <Button
            className='h-7 px-2.5 text-xs'
            render={<Link to={AGENT_PROVIDERS_ROUTE} />}
            size='sm'
            type='button'
          >
            {AGENT_PROVIDERS_COPY.guidanceAction}
          </Button>
        )}
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
