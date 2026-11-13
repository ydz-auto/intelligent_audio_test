/**
 * 会话页「平台模型供应商状态摘要」（features/agent-providers）。
 * 与供应商管理页共用 AGENT_PROVIDERS_QUERY_KEY：设为默认 / 删除 / 新增后
 * 会话页摘要随之刷新（单一缓存口径，不做局部改状态）。
 * 无可用供应商时给出「去配置」直达入口，不静默失败。
 */
import { Link } from '@tanstack/react-router'
import { AlertTriangle, Bot } from 'lucide-react'

import { usePermissions } from '@/application/hooks/use-permissions'
import {
  hasUsableProvider,
  pickDefaultProvider,
  useAgentProvidersQuery,
} from '@/application/agent/use-agent-providers'
import { Skeleton } from '@/components/ui/skeleton'

import {
  AGENT_PROVIDERS_COPY,
  AGENT_PROVIDERS_ROUTE,
  AGENT_PROVIDER_MANAGE_PERMISSION,
} from '../constants'

export function AgentProviderStatusChip({ compact = false }: { compact?: boolean }) {
  const { hasPermission } = usePermissions()
  const allowed = hasPermission(AGENT_PROVIDER_MANAGE_PERMISSION)
  const query = useAgentProvidersQuery({ enabled: allowed })

  if (!allowed) return null

  if (query.isPending) {
    return <Skeleton className='h-5 w-28 rounded' />
  }

  if (query.isError) {
    return (
      <span className='text-muted-foreground inline-flex items-center gap-1 text-[11px]'>
        <AlertTriangle className='size-3.5 text-amber-500' aria-hidden='true' />
        {AGENT_PROVIDERS_COPY.loadErrorTitle}
      </span>
    )
  }

  const provider = pickDefaultProvider(query.data)

  if (!hasUsableProvider(query.data) || !provider) {
    return (
      <Link
        className='border-warning/40 bg-warning/10 text-warning inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors hover:brightness-95'
        to={AGENT_PROVIDERS_ROUTE}
      >
        <AlertTriangle className='size-3.5' aria-hidden='true' />
        {AGENT_PROVIDERS_COPY.sessionNoProvider}
        <span aria-hidden='true'>·</span>
        <span className='underline underline-offset-2'>
          {AGENT_PROVIDERS_COPY.sessionGoConfigure}
        </span>
      </Link>
    )
  }

  return (
    <span
      className='text-muted-foreground inline-flex min-w-0 max-w-full items-center gap-1 text-[11px]'
      title={`${AGENT_PROVIDERS_COPY.sessionSummaryPrefix}：${provider.name} · ${provider.model}`}
    >
      <Bot className='size-3.5 shrink-0' aria-hidden='true' />
      <span className='shrink-0'>{AGENT_PROVIDERS_COPY.sessionSummaryPrefix}</span>
      <span className='text-foreground min-w-0 truncate font-medium'>
        {compact ? provider.model : `${provider.name} · ${provider.model}`}
      </span>
    </span>
  )
}
