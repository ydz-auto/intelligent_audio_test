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
  existingRounds,
  RoundScopeThreeField,
  usePerRoundValue,
  type ApplyLayerId,
} from '@/features/testcases/modals/batch-shared'
import {
  batchTestcaseAction,
  type TestcaseBatchPayload,
  type TestcaseRoundMode,
} from '@/infrastructure/api/testcases-batch-api'

export function BatchSplDialog({
  open,
  onOpenChange,
  count,
  ids,
  roundCount,
  unknownRoundCount = 0,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
  /** 选中用例实际轮次数（config.rounds 派生；0=空态——INT-1731/INT-1506） */
  roundCount: number
  /** 选中用例中轮次未知（列表尚未加载）的条数 */
  unknownRoundCount?: number
}) {
  const totalRounds = Math.max(1, roundCount)
  const [scope, setScope] = useState(() => createRoundScope(roundCount))
  const [layers, setLayers] = useState<ApplyLayerId[]>([])
  const [submitting, setSubmitting] = useState(false)
  const { current: spl, setCurrent: setSpl, perRound } = usePerRoundValue('', scope)

  const handleSubmit = async () => {
    const targets = applyLayerToTargets(layers)
    let payload: TestcaseBatchPayload
    if (scope.mode === 'per_round') {
      // 逐轮设置：round_values = {轮次号: {value, targets}}，仅含用户实际编辑过的真实轮次
      const roundValues: Record<string, unknown> = {}
      for (const [roundKey, roundSpl] of Object.entries(perRound)) {
        const round = Number(roundKey)
        if (!Number.isInteger(round) || round < 1 || round > totalRounds) continue
        if (roundSpl === '') continue
        const numeric = Number(roundSpl)
        if (Number.isNaN(numeric)) continue
        roundValues[roundKey] = { value: numeric, targets }
      }
      if (Object.keys(roundValues).length === 0) {
        toast.error('请至少填写一个轮次的声压级')
        return
      }
      payload = { roundMode: 'per_round', roundNumbers: [], roundValues }
    } else {
      const value = Number(spl)
      if (Number.isNaN(value) || spl === '') return
      const roundNumbers =
        scope.mode === 'specific' ? existingRounds(scope.specificRounds, totalRounds) : undefined
      // 指定轮次未勾选任何真实轮次：不提交（后端对不存在/空轮次静默回成功——INT-1731）
      if (roundNumbers && roundNumbers.length === 0) {
        toast.error('请至少选择一个轮次')
        return
      }
      payload = {
        spl: { value },
        targets,
        roundMode: scope.mode as TestcaseRoundMode,
        roundNumbers,
      }
    }
    setSubmitting(true)
    try {
      await batchTestcaseAction('update_spl', ids, payload)
      toast.success(`批量操作执行成功（更新 ${count} 个）`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量设置声压级失败')
    } finally {
      setSubmitting(false)
    }
  }

  /** 逐轮模式：任一编辑过的轮次有有效值即可提交 */
  const canSubmit =
    scope.mode === 'per_round'
      ? Object.values(perRound).some((v) => v !== '' && !Number.isNaN(Number(v)))
      : spl !== '' && !Number.isNaN(Number(spl))

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

          <ApplyLayerField
            value={layers}
            onChange={setLayers}
            hint='可多选；留空时默认应用到目标人音频'
          />
          <RoundScopeThreeField
            name='batch-spl-round'
            value={scope}
            onChange={setScope}
            roundCount={roundCount}
            unknownRoundCount={unknownRoundCount}
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || !canSubmit}>
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
