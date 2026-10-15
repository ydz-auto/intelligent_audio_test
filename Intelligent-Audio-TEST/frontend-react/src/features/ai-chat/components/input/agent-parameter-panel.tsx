/**
 * 生成参数面板（interfaces 层 ai-chat/input；08_AI对话页.md §3.5 照 newAPI playground-parameter-panel）：
 * 六参数注册表驱动（温度/Top P/频率惩罚/存在惩罚/最大 Tokens/随机种子），激活计数角标；
 * 桌面 Popover w-[22rem]，移动 Sheet bottom max-h-[85vh]。
 */
import { SlidersHorizontal } from 'lucide-react'

import { PromptInputButton } from '@/components/ai-elements/prompt-input'
import { Badge } from '@/components/ui/badge'
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
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'

import type { ChatConfig, ChatParameterKey } from '@/domain/models/aiChat'
import {
  AGENT_PARAMETER_CONTROLS,
  type AgentParameterControl,
} from '@/features/ai-chat/constants'
import {
  getParameterControlValueText,
  normalizeParameterNumberValue,
} from '@/features/ai-chat/lib/parameters'

type AgentParameterPanelProps = {
  config: ChatConfig
  disabled?: boolean
  onConfigChange: <K extends keyof ChatConfig>(
    key: K,
    value: ChatConfig[K]
  ) => void
  onParameterEnabledChange: (key: ChatParameterKey, value: boolean) => void
  parameterEnabled: Record<ChatParameterKey, boolean>
}

function ParameterControl({
  control,
  value,
  enabled,
  disabled,
  onChange,
  onEnabledChange,
}: {
  control: AgentParameterControl
  value: number | null
  enabled: boolean
  disabled: boolean
  onChange: (key: ChatParameterKey, value: number | null) => void
  onEnabledChange: (key: ChatParameterKey, value: boolean) => void
}) {
  const controlId = `agent-param-${control.key}`

  return (
    <div
      className={cn(
        'border-border/70 bg-background/60 grid gap-2 rounded-lg border p-3 transition-opacity',
        (!enabled || disabled) && 'opacity-55'
      )}
    >
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0 space-y-1'>
          <div className='flex min-w-0 items-center gap-2'>
            <label
              className='truncate text-sm leading-5 font-medium'
              htmlFor={controlId}
            >
              {control.label}
            </label>
            <Badge className='h-5 max-w-24 shrink-0 px-1.5 font-mono text-[11px]' variant='outline'>
              {getParameterControlValueText(control.key, value)}
            </Badge>
          </div>
          <p className='text-muted-foreground text-xs leading-4'>
            {control.description}
          </p>
        </div>

        <Switch
          aria-label={`启用 ${control.label}`}
          checked={enabled}
          disabled={disabled}
          onCheckedChange={(checked) => onEnabledChange(control.key, checked)}
          size='sm'
        />
      </div>

      {control.valueType === 'slider' ? (
        <Slider
          className='py-1.5'
          disabled={disabled || !enabled}
          id={controlId}
          max={control.max}
          min={control.min}
          onValueChange={(nextValue) => {
            const firstValue = Array.isArray(nextValue)
              ? nextValue[0]
              : nextValue
            onChange(
              control.key,
              normalizeParameterNumberValue(control.key, firstValue)
            )
          }}
          step={control.step}
          value={[Number(value)]}
        />
      ) : (
        <Input
          disabled={disabled || !enabled}
          id={controlId}
          inputMode='numeric'
          max={control.max}
          min={control.min}
          onChange={(event) => {
            onChange(
              control.key,
              normalizeParameterNumberValue(control.key, event.target.value)
            )
          }}
          step={control.step}
          type='number'
          value={value ?? ''}
        />
      )}
    </div>
  )
}

export function AgentParameterPanel(props: AgentParameterPanelProps) {
  const isMobile = useIsMobile()
  const activeCount = AGENT_PARAMETER_CONTROLS.filter(
    (control) => props.parameterEnabled[control.key]
  ).length

  const updateParameterConfig = (key: ChatParameterKey, value: number | null) => {
    if (key === 'seed') {
      props.onConfigChange('seed', value)
      return
    }
    props.onConfigChange(key, value ?? 0)
  }

  const trigger = (
    <PromptInputButton
      aria-label='生成参数'
      className='text-muted-foreground hover:text-foreground hover:bg-muted/70 relative font-medium'
      disabled={props.disabled}
      variant='ghost'
    >
      <SlidersHorizontal className='size-4' />
      <span className='bg-primary text-primary-foreground absolute -top-1 -right-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full px-1 text-[9px] leading-none font-semibold'>
        {activeCount}
      </span>
    </PromptInputButton>
  )

  const content = (
    <div className='max-h-[min(28rem,calc(100vh-10rem))] grid gap-3 overflow-y-auto pr-1'>
      {AGENT_PARAMETER_CONTROLS.map((control) => (
        <ParameterControl
          control={control}
          disabled={props.disabled ?? false}
          enabled={props.parameterEnabled[control.key]}
          key={control.key}
          onChange={updateParameterConfig}
          onEnabledChange={props.onParameterEnabledChange}
          value={props.config[control.key] as number | null}
        />
      ))}
    </div>
  )

  if (isMobile) {
    return (
      <Sheet>
        <Tooltip>
          <TooltipTrigger render={<SheetTrigger render={trigger} />} />
          <TooltipContent>
            <p>生成参数</p>
          </TooltipContent>
        </Tooltip>
        <SheetContent className='max-h-[85vh] overflow-hidden rounded-t-xl' side='bottom'>
          <SheetHeader>
            <SheetTitle>生成参数</SheetTitle>
          </SheetHeader>
          <div className='px-4 pb-4'>{content}</div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger render={<PopoverTrigger render={trigger} />} />
        <TooltipContent>
          <p>生成参数</p>
        </TooltipContent>
      </Tooltip>
      <PopoverContent
        align='start'
        className='w-[22rem] max-w-[calc(100vw-2rem)] gap-3 p-3'
        collisionPadding={8}
        side='top'
        sideOffset={8}
      >
        <div className='space-y-1 px-1'>
          <div className='text-sm font-semibold'>生成参数</div>
          <div className='text-muted-foreground text-xs leading-4'>
            只有启用的参数会随请求发送。
          </div>
        </div>
        {content}
      </PopoverContent>
    </Popover>
  )
}
