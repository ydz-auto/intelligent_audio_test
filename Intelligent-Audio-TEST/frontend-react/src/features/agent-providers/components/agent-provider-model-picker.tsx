/**
 * 对话页「供应商 + 模型」选择器（features/agent-providers）。
 *
 * - 供应商：列出当前用户可用的供应商；选择只影响本轮 run 的 Key / Base URL，
 *   不改变全局默认（后端按 owner + tenant 校验归属）；
 * - 模型：按所选供应商拉取 /models 探测结果（与「自动发现模型」同源，5 分钟缓存），
 *   失败时至少保留该供应商配置的模型；
 * - 选择结果写入会话 config.providerId / config.modelId，由下一次 run 下发。
 */
import { Link } from '@tanstack/react-router'
import { AlertTriangle, Bot } from 'lucide-react'
import { useMemo } from 'react'

import {
  hasUsableProvider,
  pickDefaultProvider,
  useAgentProviderModelsQuery,
  useAgentProvidersQuery,
} from '@/application/agent/use-agent-providers'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

import { AGENT_PROVIDERS_COPY, AGENT_PROVIDERS_ROUTE } from '../constants'

type AgentProviderModelPickerProps = {
  /** 当前会话选中的供应商（空=默认供应商） */
  providerId?: string
  /** 当前会话选中的模型（空=供应商配置的模型） */
  model?: string
  onProviderChange: (providerId: string) => void
  onModelChange: (model: string) => void
  compact?: boolean
}

function ModelSelect({
  providerId,
  providerModel,
  model,
  onModelChange,
  compact,
}: {
  providerId: string
  providerModel: string
  model?: string
  onModelChange: (model: string) => void
  compact: boolean
}) {
  const modelsQuery = useAgentProviderModelsQuery(providerId)
  const items = useMemo(() => {
    const names = new Set<string>(modelsQuery.data ?? [])
    if (providerModel) names.add(providerModel)
    if (model) names.add(model)
    return [...names].map((name) => ({ value: name, label: name }))
  }, [modelsQuery.data, providerModel, model])

  return (
    <Select
      items={items}
      value={model || providerModel || null}
      onValueChange={(next) => {
        if (next) onModelChange(next)
      }}
    >
      <SelectTrigger
        aria-label={AGENT_PROVIDERS_COPY.modelSelectAria}
        className={
          compact
            ? 'h-7 w-auto max-w-44 min-w-0 text-[11px]'
            : 'h-7 w-auto max-w-64 min-w-0 text-xs'
        }
        size='sm'
      >
        <SelectValue
          placeholder={
            modelsQuery.isPending
              ? AGENT_PROVIDERS_COPY.modelSelectLoading
              : AGENT_PROVIDERS_COPY.modelSelectPlaceholder
          }
        />
      </SelectTrigger>
      <SelectContent>
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function AgentProviderModelPicker({
  providerId,
  model,
  onProviderChange,
  onModelChange,
  compact = false,
}: AgentProviderModelPickerProps) {
  const query = useAgentProvidersQuery({ enabled: true })

  if (query.isPending) {
    return <Skeleton className='h-5 w-40 rounded' />
  }

  if (query.isError) {
    return (
      <span className='text-muted-foreground inline-flex items-center gap-1 text-[11px]'>
        <AlertTriangle className='size-3.5 text-amber-500' aria-hidden='true' />
        {AGENT_PROVIDERS_COPY.loadErrorTitle}
      </span>
    )
  }

  if (!hasUsableProvider(query.data)) {
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

  const providers = query.data ?? []
  const selected =
    providers.find((provider) => provider.id === providerId) ??
    pickDefaultProvider(providers) ??
    providers[0]
  const providerItems = providers.map((provider) => ({
    value: provider.id,
    label: provider.name,
  }))

  return (
    <div className='flex min-w-0 flex-wrap items-center gap-2'>
      <Bot className='text-muted-foreground size-3.5 shrink-0' aria-hidden='true' />
      <Select
        items={providerItems}
        value={selected?.id ?? null}
        onValueChange={(next) => {
          if (next) onProviderChange(next)
        }}
      >
        <SelectTrigger
          aria-label={AGENT_PROVIDERS_COPY.providerSelectAria}
          className={
            compact
              ? 'h-7 w-auto max-w-40 min-w-0 text-[11px]'
              : 'h-7 w-auto max-w-56 min-w-0 text-xs'
          }
          size='sm'
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {providerItems.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selected && (
        <ModelSelect
          compact={compact}
          model={model}
          onModelChange={onModelChange}
          providerId={selected.id}
          providerModel={selected.model}
        />
      )}
    </div>
  )
}
