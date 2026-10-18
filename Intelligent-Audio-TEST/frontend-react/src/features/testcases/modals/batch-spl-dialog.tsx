/**
 * 批量设置声压级弹窗（11_用例域.md §5.3.3，Dialog sm:max-w-md；INT-710 真实数据接线）。
 * 声压级 dB*（number，占位「请输入声压级，例如：65」）+ 应用层级多选（五项，可多选）
 * + 轮次范围三档「所有轮次（统一设置）/指定轮次（统一设置）/逐轮设置（每轮可不同）」。
 * 提交走 POST /testcases/batch（update_spl）：spl.value + targets + round_mode/round_numbers。
 */
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import {
  applyLayerToTargets,
  ApplyLayerField,
  createRoundScope,
  RoundScopeThreeField,
  usePerRoundValue,
  type ApplyLayerId,
} from '@/features/testcases/modals/batch-shared'
import {
  batchTestcaseAction,
  type TestcaseRoundMode,
} from '@/infrastructure/api/testcases-batch-api'

export function BatchSplDialog({
  open,
  onOpenChange,
  count,
  ids,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
}) {
  const [scope, setScope] = useState(createRoundScope())
  const [layers, setLayers] = useState<ApplyLayerId[]>([])
  const [submitting, setSubmitting] = useState(false)
  const { current: spl, setCurrent: setSpl } = usePerRoundValue('', scope)

  const handleSubmit = async () => {
    const value = Number(spl)
    if (Number.isNaN(value)) return
    setSubmitting(true)
    try {
      await batchTestcaseAction('update_spl', ids, {
        spl: { value },
        targets: applyLayerToTargets(layers),
        roundMode: scope.mode as TestcaseRoundMode,
        roundNumbers:
          scope.mode === 'specific' ? scope.specificRounds : undefined,
      })
      toast.success(`批量操作执行成功（更新 ${count} 个）`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量设置声压级失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>批量设置声压级</DialogTitle>
          <DialogDescription>
            您勾选了 {count} 个用例，将统一设置其声压级
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>
              {scope.mode === 'per_round' ? `第 ${scope.activeRound} 轮声压级 dB *` : '声压级 dB *'}
            </span>
            <Input
              type='number'
              min={0}
              max={140}
              value={spl}
              onChange={(e) => setSpl(e.target.value)}
              placeholder='请输入声压级，例如：65'
              className='h-8'
              aria-label='声压级 dB'
            />
          </div>

          <ApplyLayerField value={layers} onChange={setLayers} />
          <RoundScopeThreeField
            name='batch-spl-round'
            value={scope}
            onChange={setScope}
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || Number.isNaN(Number(spl))}>
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
