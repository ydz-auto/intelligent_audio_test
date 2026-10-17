/**
 * 挑选合并四步向导壳（18_挑选合并交互重设计.md §5.1/§7.1，INT-600）。
 * 页内状态机：挑选→购物车→复核→下单；Stepper 步进；筛选条件会话级记忆（§6.4，不持久化）。
 * 批量浮条「加入挑选」预选任务进入时 presetTaskIds 生效。
 */
import { ArrowLeft } from 'lucide-react'
import { useEffect, useState } from 'react'

import type { PickFilters } from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import { EMPTY_PICK_FILTERS } from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { WizardStepKey } from '@/features/tasks/cherry-pick/constants'
import { WIZARD_STEPS } from '@/features/tasks/cherry-pick/constants'
import { PickStep } from '@/features/tasks/cherry-pick/steps/pick-step'
import { CartStep } from '@/features/tasks/cherry-pick/steps/cart-step'
import { ReviewStep } from '@/features/tasks/cherry-pick/steps/review-step'
import { CheckoutStep } from '@/features/tasks/cherry-pick/steps/checkout-step'

function Stepper({
  current,
  onStepChange,
}: {
  current: WizardStepKey
  onStepChange: (step: WizardStepKey) => void
}) {
  const currentIndex = WIZARD_STEPS.findIndex((s) => s.key === current)
  return (
    <nav aria-label='挑选合并向导步骤' className='flex flex-wrap items-center gap-1'>
      {WIZARD_STEPS.map((step, i) => {
        const done = i < currentIndex
        const active = i === currentIndex
        const reachable = i <= currentIndex
        return (
          <button
            key={step.key}
            type='button'
            data-testid={`wizard-step-${step.key}`}
            className='flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60'
            disabled={!reachable}
            onClick={() => onStepChange(step.key)}
          >
            <span
              className={cn(
                'flex size-5 items-center justify-center rounded-full text-xs font-medium',
                done
                  ? 'bg-primary text-primary-foreground'
                  : active
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground'
              )}
            >
              {i + 1}
            </span>
            <span
              className={cn(
                'font-medium',
                active ? 'text-foreground' : 'text-muted-foreground'
              )}
            >
              {step.label}
            </span>
            {i < WIZARD_STEPS.length - 1 && (
              <span className='text-muted-foreground/40 mx-0.5'>›</span>
            )}
          </button>
        )
      })}
    </nav>
  )
}

export function CherryPickWizard({
  open,
  step,
  onStepChange,
  onClose,
  presetTaskIds,
}: {
  open: boolean
  step: WizardStepKey
  onStepChange: (step: WizardStepKey) => void
  onClose: () => void
  /** 批量「加入挑选」预选任务（进入向导即预选该批任务） */
  presetTaskIds?: number[]
}) {
  const [filters, setFilters] = useState<PickFilters>(EMPTY_PICK_FILTERS)
  const [lastPreset, setLastPreset] = useState<number[] | undefined>(undefined)

  // 打开时：预选任务 + 初始化购物车镜像
  useEffect(() => {
    if (open) {
      void usePickCartStore.getState().refreshCart()
      if (presetTaskIds && presetTaskIds !== lastPreset) {
        setLastPreset(presetTaskIds)
        setFilters({ ...EMPTY_PICK_FILTERS, taskIds: presetTaskIds })
      }
    }
  }, [open, presetTaskIds, lastPreset])

  if (!open) return null

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <Stepper current={step} onStepChange={onStepChange} />
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-7 gap-1 text-xs'
          onClick={onClose}
        >
          <ArrowLeft aria-hidden='true' className='size-3.5' />
          返回列表
        </Button>
      </div>

      <div className='min-h-0 flex-1'>
        {step === 'pick' && (
          <PickStep
            filters={filters}
            onFiltersChange={setFilters}
            onResetFilters={() => setFilters(EMPTY_PICK_FILTERS)}
            onAdded={() => onStepChange('cart')}
          />
        )}
        {step === 'cart' && (
          <CartStep onGoPick={() => onStepChange('pick')} onGoReview={() => onStepChange('review')} />
        )}
        {step === 'review' && (
          <ReviewStep onGoPick={() => onStepChange('pick')} onGoCheckout={() => onStepChange('checkout')} />
        )}
        {step === 'checkout' && <CheckoutStep onGoReview={() => onStepChange('review')} onDone={onClose} />}
      </div>
    </div>
  )
}
