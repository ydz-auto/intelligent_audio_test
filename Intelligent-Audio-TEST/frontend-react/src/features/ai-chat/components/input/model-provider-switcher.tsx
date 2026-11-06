/**
 * 模型/供应商切换器（interfaces 层 ai-chat/input；08_AI对话页.md §3.5）。
 * 对位 newAPI ModelGroupSelector 双列版式（model-group-selector/layout.ts 类值照搬），
 * 左列=供应商（用户自管 LLM API 供应商清单 §3.11），右列=该供应商可用模型；
 * 无参数面板（2026-10-17 负责人口径：仅允许切换模型与供应商）。
 * 无供应商时整钮渲染空态提示「未配置 LLM 供应商 → 点击配置」，点击直接开 §3.11 管理弹窗。
 */
import { Check, ChevronsUpDown, Cpu, Settings2 } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'

import type { ChatConfig, LlmProvider } from '@/domain/models/aiChat'
import { MODEL_PROVIDER_COPY } from '@/features/ai-chat/constants'

const LAYOUT = {
  panel: 'max-h-[min(50vh,28rem)] overflow-hidden',
  content:
    'grid h-[min(50vh,28rem)] max-h-[min(50vh,28rem)] min-h-0 gap-3 p-2 md:grid-cols-[9.5rem_minmax(0,1fr)]',
  groupScroll:
    'mt-2 grid min-h-0 flex-1 auto-rows-[2rem] content-start gap-1 overflow-y-auto pr-1',
  modelColumn: 'flex h-full min-h-0 min-w-0 overflow-hidden rounded-lg border',
  modelList:
    'min-h-0 flex-1 max-h-none [scrollbar-color:var(--border)_transparent] [scrollbar-width:thin] [&::-webkit-scrollbar]:block [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent',
  modelItem:
    'relative mb-0.5 flex items-center justify-between rounded-md border border-transparent px-2 py-1.5 pl-3 text-[12px] leading-4 transition-colors before:absolute before:inset-y-2 before:left-1 before:w-1 before:rounded-full before:bg-transparent',
  selectedItem: 'border-primary/40 bg-primary/12 text-foreground shadow-sm before:bg-primary',
  unselectedItem: 'text-muted-foreground hover:bg-accent hover:text-foreground',
} as const

type ModelProviderSwitcherProps = {
  providers: LlmProvider[]
  config: ChatConfig
  onSelectProvider: (providerId: string) => void
  onSelectModel: (providerId: string, modelId: string) => void
  onManageProviders: () => void
  disabled?: boolean
  className?: string
}

export function ModelProviderSwitcher({
  providers,
  config,
  onSelectProvider,
  onSelectModel,
  onManageProviders,
  disabled,
  className,
}: ModelProviderSwitcherProps) {
  const isMobile = useIsMobile()
  const [open, setOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeProviderId, setActiveProviderId] = useState<string | null>(
    config.providerId ?? null
  )

  const defaultProvider = providers.find((p) => p.isDefault) ?? providers[0] ?? null
  const currentProvider =
    providers.find((p) => p.id === config.providerId) ?? defaultProvider
  const currentModel = currentProvider?.models.find((m) => m === config.modelId) ?? null

  const activeProvider =
    providers.find((p) => p.id === activeProviderId) ?? defaultProvider ?? null

  const filteredModels = useMemo(() => {
    if (!activeProvider) return []
    const query = searchQuery.trim().toLowerCase()
    if (!query) return activeProvider.models
    return activeProvider.models.filter((model) => model.toLowerCase().includes(query))
  }, [activeProvider, searchQuery])

  /** 无供应商：整钮渲染空态提示，点击直接开管理弹窗（§3.5） */
  if (providers.length === 0) {
    return (
      <Button
        className={cn(
          'h-8 max-w-[15rem] justify-start gap-2 border px-2.5 font-medium shadow-none',
          'bg-background/80 hover:bg-accent/70 text-foreground focus:!ring-0 focus:!outline-none',
          className
        )}
        disabled={disabled}
        onClick={onManageProviders}
        size='sm'
        type='button'
        variant='outline'
      >
        <Cpu className='text-muted-foreground size-4 shrink-0' />
        <span className='min-w-0 truncate text-xs'>
          {MODEL_PROVIDER_COPY.noProvider}
        </span>
      </Button>
    )
  }

  const trigger = (
    <Button
      aria-expanded={open}
      className={cn(
        'h-8 max-w-[15rem] justify-start gap-2 border px-2.5 font-medium shadow-none',
        'bg-background/80 hover:bg-accent/70 text-foreground focus:!ring-0 focus:!outline-none',
        className
      )}
      disabled={disabled}
      role='combobox'
      size='sm'
      type='button'
      variant='outline'
    >
      <Cpu className='text-muted-foreground size-4 shrink-0' />
      <span className='min-w-0 truncate text-xs'>
        {currentModel ?? MODEL_PROVIDER_COPY.selectModel}
      </span>
      {currentProvider && (
        <span className='bg-muted text-muted-foreground hidden max-w-20 shrink-0 rounded px-1.5 py-0.5 text-[10px] sm:inline-flex'>
          {currentProvider.name}
        </span>
      )}
      <ChevronsUpDown className='text-muted-foreground ml-auto size-3.5 shrink-0 opacity-60' />
    </Button>
  )

  const content = (
    <div className={cn('min-h-0', isMobile ? 'grid gap-3 p-2' : LAYOUT.content)}>
      {/* 左列：供应商（用户自管清单，§3.11） */}
      <div className='flex h-full min-h-0 min-w-0 flex-col overflow-hidden'>
        <div className='text-muted-foreground px-1 text-[11px] leading-4 font-medium'>
          {MODEL_PROVIDER_COPY.selectProvider}
        </div>
        <div className={cn('grid gap-1', LAYOUT.groupScroll)}>
          {providers.map((provider) => {
            const isActive = activeProvider?.id === provider.id
            const isCurrent = currentProvider?.id === provider.id
            return (
              <button
                aria-pressed={isActive}
                className={cn(
                  'flex min-w-0 items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-[12px] leading-4 transition-colors',
                  isActive || isCurrent
                    ? 'bg-primary/10 text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
                key={provider.id}
                onClick={() => {
                  setActiveProviderId(provider.id)
                  // 供应商切换即写会话 config（§3.5；模型待右列选择）
                  onSelectProvider(provider.id)
                }}
                type='button'
              >
                <span className='min-w-0 truncate font-medium'>
                  {provider.name}
                  {provider.isDefault ? '（默认）' : ''}
                </span>
                <Check
                  className={cn(
                    'size-3.5 shrink-0',
                    isCurrent ? 'opacity-100' : 'opacity-0'
                  )}
                />
              </button>
            )
          })}
        </div>
        <button
          className='hover:bg-accent text-muted-foreground mt-2 flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-2 text-left text-[12px] leading-4 transition-colors'
          onClick={() => {
            setOpen(false)
            onManageProviders()
          }}
          type='button'
        >
          <Settings2 className='size-3.5 shrink-0' />
          {MODEL_PROVIDER_COPY.manageProviders}
        </button>
      </div>

      {/* 右列：该供应商可用模型 */}
      <div className={cn('min-w-0 overflow-hidden rounded-lg border', LAYOUT.modelColumn)}>
        <div className='flex min-h-0 w-full flex-1 flex-col p-1'>
          <Input
            className='h-8 text-[13px]'
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder='搜索模型…'
            value={searchQuery}
          />
          <div className={cn('mt-1 overflow-y-auto', LAYOUT.modelList)}>
            {filteredModels.length === 0 ? (
              <div className='text-muted-foreground px-3 py-8 text-center text-[12px] leading-5'>
                未找到匹配模型
              </div>
            ) : (
              filteredModels.map((model) => {
                const isSelected = currentModel === model && currentProvider?.id === activeProvider?.id
                return (
                  <button
                    className={cn(
                      LAYOUT.modelItem,
                      isSelected ? LAYOUT.selectedItem : LAYOUT.unselectedItem
                    )}
                    key={model}
                    onClick={() => {
                      onSelectModel(activeProvider?.id ?? '', model)
                      setOpen(false)
                    }}
                    type='button'
                  >
                    <span
                      className={cn(
                        'min-w-0 truncate',
                        isSelected ? 'font-semibold text-foreground' : 'font-medium'
                      )}
                    >
                      {model}
                    </span>
                    <Check
                      className={cn(
                        'size-3.5 shrink-0',
                        isSelected ? 'opacity-100' : 'opacity-0'
                      )}
                    />
                  </button>
                )
              })
            )}
          </div>
        </div>
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger render={trigger} />
        <SheetContent className='max-h-[80vh] min-h-[60vh] overflow-hidden rounded-t-xl' side='bottom'>
          <SheetHeader>
            <SheetTitle className='flex items-center gap-2 text-left text-lg font-medium'>
              <Cpu className='size-4' />
              选择模型与供应商
            </SheetTitle>
          </SheetHeader>
          {content}
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={trigger} />
      <PopoverContent
        align='end'
        className={cn(
          'bg-popover z-50 w-[34rem] max-w-[calc(100vw-2rem)] rounded-xl border p-0 shadow-lg',
          LAYOUT.panel
        )}
        collisionPadding={8}
        side='top'
        sideOffset={8}
      >
        {content}
      </PopoverContent>
    </Popover>
  )
}
