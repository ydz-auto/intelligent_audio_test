/**
 * FlowSteps 流程步骤条（interfaces/features/test-execution/components；平台件，10_测试执行.md §6）。
 * 照 setup-wizard STEPS 卡格通用化：`ol grid gap-2.5 sm:grid-cols-5`，每格 rounded-xl border p-3；
 * 三态——当前 border-primary ring-primary/20 ring-2 / 已完成 border-primary/40 bg-primary/5 /
 * 未到 border-muted bg-card；数字圆标 size-6 rounded-md border，已完成位换 CheckCircle2。
 * 只读观察态（§3.1.1）：步骤条可点击翻页浏览，但不触发校验/解锁语义。
 */
import { CheckCircle2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { FlowStep } from '@/application/test-execution/useFlowSteps'
import type { FlowStepDefinition } from '@/features/test-execution/constants'

interface FlowStepsProps {
  steps: FlowStepDefinition[]
  current: FlowStep
  /** 已完成（current 之前且已解锁） */
  done: (index: number) => boolean
  onNavigate: (index: number) => void
  disabledHint?: (index: number) => string | null
  readOnly?: boolean
}

export function FlowSteps({
  steps,
  current,
  done,
  onNavigate,
  disabledHint,
  readOnly = false,
}: FlowStepsProps) {
  return (
    <ol className='grid grid-cols-2 gap-2.5 sm:grid-cols-5 sm:gap-3'>
      {steps.map((step) => {
        const isCurrent = step.index === current
        const isDone = done(step.index) && !isCurrent
        const hint = disabledHint?.(step.index)
        const isDisabled = Boolean(hint) && !readOnly

        return (
          <li key={step.index}>
            <button
              type='button'
              aria-current={isCurrent ? 'step' : undefined}
              disabled={isDisabled}
              title={hint ?? undefined}
              onClick={() => onNavigate(step.index)}
              className={cn(
                'flex w-full items-start gap-3 rounded-xl border p-3 text-start transition-colors',
                isCurrent && 'border-primary ring-primary/20 ring-2',
                isDone && 'border-primary/40 bg-primary/5 hover:bg-primary/10',
                !isCurrent && !isDone && 'border-muted bg-card hover:bg-muted/40',
                isDisabled && 'cursor-not-allowed opacity-60',
                readOnly && 'cursor-pointer'
              )}
            >
              <span
                aria-hidden='true'
                className={cn(
                  'flex size-6 shrink-0 items-center justify-center rounded-md border text-xs font-semibold',
                  (isCurrent || isDone) && 'border-primary bg-primary text-primary-foreground',
                  !isCurrent && !isDone && 'border-muted-foreground/40 text-muted-foreground'
                )}
              >
                {isDone ? (
                  <CheckCircle2 className='size-3.5' />
                ) : (
                  step.index + 1
                )}
              </span>
              <span className='min-w-0'>
                <span className={cn('block truncate text-sm font-semibold')}>
                  {step.title}
                </span>
                <span className='text-muted-foreground mt-0.5 block truncate text-xs'>
                  {step.description}
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
