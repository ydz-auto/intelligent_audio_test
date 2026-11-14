/**
 * Auto 预算设置（interfaces 层 ai-chat/auto-mode；INT-2474 §9.4 / 拍板增补 2）。
 *
 * 「启动 Auto 前必须展示计划与预算」：选 Auto 后输入区上方直接展示五个维度
 * 的收紧输入（留空 = 用服务端默认），并标明默认值口径与「只能收紧」。
 *
 * 输入是字符串草稿：非法输入（0 / 负数 / 非数字）只标红、不进入请求；
 * 合法值实时回写会话 config（整页 / 浮窗共用同一份预算）。
 */
import { ChevronDown, Gauge } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Input } from '@/components/ui/input'
import { AGENT_AUTO_COPY, type AgentRunBudget } from '@/domain/models/agent'
import {
  buildAutoBudget,
  budgetsEqual,
  invalidBudgetFields,
  toAutoBudgetDraft,
  type AutoBudgetDraft,
} from '@/features/ai-chat/lib/auto-budget'
import { cn } from '@/lib/utils'

/** 五个输入项（键 → 文案 / 单位 / placeholder / inputMode） */
const BUDGET_FIELDS: Array<{
  key: keyof AutoBudgetDraft
  label: string
  unit: string
}> = [
  { key: 'maxRounds', label: AGENT_AUTO_COPY.budgetRounds, unit: AGENT_AUTO_COPY.unitRounds },
  {
    key: 'maxToolCalls',
    label: AGENT_AUTO_COPY.budgetToolCalls,
    unit: AGENT_AUTO_COPY.unitToolCalls,
  },
  { key: 'maxTokens', label: AGENT_AUTO_COPY.budgetTokens, unit: AGENT_AUTO_COPY.unitTokens },
  {
    key: 'maxDurationMinutes',
    label: AGENT_AUTO_COPY.budgetDuration,
    unit: AGENT_AUTO_COPY.unitMinutes,
  },
  {
    key: 'maxOutputMegabytes',
    label: AGENT_AUTO_COPY.budgetOutput,
    unit: AGENT_AUTO_COPY.unitMegabytes,
  },
]

type AutoBudgetSettingsProps = {
  /** 会话 config 里的预算（唯一事实源；外部变化时同步草稿） */
  budget?: AgentRunBudget
  onBudgetChange: (budget: AgentRunBudget | undefined) => void
  disabled?: boolean
}

export function AutoBudgetSettings({
  budget,
  onBudgetChange,
  disabled = false,
}: AutoBudgetSettingsProps) {
  const [open, setOpen] = useState(true)
  const [draft, setDraft] = useState<AutoBudgetDraft>(() =>
    toAutoBudgetDraft(budget)
  )
  /** 最近一次由本组件写出的预算（外部同步时用来判断是否自己的回声） */
  const emittedRef = useRef<AgentRunBudget | undefined>(buildAutoBudget(draft))

  // 另一宿主 / 会话切换改了预算：草稿跟着同步（自己的回声不覆盖输入框）
  useEffect(() => {
    if (budgetsEqual(emittedRef.current, budget)) return
    setDraft(toAutoBudgetDraft(budget))
    emittedRef.current = budget
  }, [budget])

  const invalid = invalidBudgetFields(draft)

  const handleChange = (key: keyof AutoBudgetDraft, value: string) => {
    const next = { ...draft, [key]: value }
    setDraft(next)
    const parsed = buildAutoBudget(next)
    emittedRef.current = parsed
    onBudgetChange(parsed)
  }

  return (
    <div
      className='border-border/50 bg-muted/15 dark:bg-muted/10 mx-3 mt-2.5 rounded-lg border'
      data-auto-budget-settings
    >
      <button
        aria-expanded={open}
        className='flex w-full items-center gap-1.5 px-3 py-2 text-left'
        onClick={() => setOpen((value) => !value)}
        type='button'
      >
        <Gauge className='text-muted-foreground size-3.5 shrink-0' />
        <span className='text-xs font-medium'>{AGENT_AUTO_COPY.budgetTitle}</span>
        <span className='text-muted-foreground truncate text-[11px]'>
          {AGENT_AUTO_COPY.budgetHint}
        </span>
        <ChevronDown
          className={cn(
            'text-muted-foreground ml-auto size-3.5 shrink-0 transition-transform',
            open && 'rotate-180'
          )}
        />
      </button>
      {open && (
        <div className='px-3 pb-2.5'>
          <div className='grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5'>
            {BUDGET_FIELDS.map((field) => {
              const isInvalid = invalid.has(field.key)
              return (
                <label className='grid gap-1' key={field.key}>
                  <span className='text-muted-foreground text-[11px] leading-4'>
                    {field.label}
                  </span>
                  <span className='relative flex items-center'>
                    <Input
                      aria-invalid={isInvalid || undefined}
                      className='h-7 rounded-md pr-9 text-xs'
                      disabled={disabled}
                      inputMode='numeric'
                      onChange={(event) =>
                        handleChange(field.key, event.target.value)
                      }
                      placeholder={AGENT_AUTO_COPY.budgetPlaceholderDefault}
                      value={draft[field.key]}
                    />
                    <span className='text-muted-foreground pointer-events-none absolute right-2 text-[10px]'>
                      {field.unit}
                    </span>
                  </span>
                </label>
              )
            })}
          </div>
          <p className='text-muted-foreground mt-1.5 text-[11px] leading-4'>
            {AGENT_AUTO_COPY.budgetDefaultHint}
          </p>
          <p className='text-muted-foreground mt-0.5 text-[11px] leading-4'>
            {AGENT_AUTO_COPY.budgetOverLimitHint}
          </p>
          {invalid.size > 0 && (
            <p className='text-destructive mt-1 text-[11px]' role='alert'>
              {AGENT_AUTO_COPY.budgetInvalid}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
