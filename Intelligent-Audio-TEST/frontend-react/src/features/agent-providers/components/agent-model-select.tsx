/**
 * 对话页模型下拉（features/agent-providers）：在默认供应商的可用模型之间切换。
 * 模型清单优先用上游 /models 探测结果（与「自动发现模型」同源），失败时至少保留
 * 供应商当前配置的模型；选择结果写入会话 config.modelId，由下一次 run 下发。
 */
import { useMemo } from 'react'

import {
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

import { AGENT_PROVIDERS_COPY } from '../constants'

type AgentModelSelectProps = {
  /** 当前选中模型（config.modelId）；空=沿用供应商默认模型 */
  model?: string
  onModelChange: (model: string) => void
  compact?: boolean
}

export function AgentModelSelect({
  model,
  onModelChange,
  compact = false,
}: AgentModelSelectProps) {
  const providers = useAgentProvidersQuery()
  const provider = pickDefaultProvider(providers.data)
  const modelsQuery = useAgentProviderModelsQuery(provider?.id)

  const modelItems = useMemo(() => {
    const names = new Set<string>(modelsQuery.data ?? [])
    if (provider?.model) names.add(provider.model)
    if (model) names.add(model)
    return [...names].map((name) => ({ value: name, label: name }))
  }, [modelsQuery.data, provider?.model, model])

  if (!provider) return null

  const value = model || provider.model || null

  return (
    <Select
      items={modelItems}
      value={value}
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
        {modelItems.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
