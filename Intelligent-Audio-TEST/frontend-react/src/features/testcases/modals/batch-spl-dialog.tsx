/**
 * 批量设置声压级弹窗（11_用例域.md §5.3.3，Dialog sm:max-w-md）。
 * 声压级 dB*（number，占位「请输入声压级，例如：65」）+ 应用层级多选（五项，可多选）
 * + 轮次范围三档「所有轮次（统一设置）/指定轮次（统一设置）/逐轮设置（每轮可不同）」
 * （§5.3.5 口径；负责人反馈「其他批量操作也是三档轮次范围逐项可用」）。
 * 可视稿演示态：提交走 toast；数据契约 spl/roundMode/rounds/appliedLayers 留接线批次。
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
import {
  ApplyLayerField,
  createRoundScope,
  RoundScopeThreeField,
  usePerRoundValue,
} from '@/features/testcases/modals/batch-shared'

export function BatchSplDialog({
  open,
  onOpenChange,
  count,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
}) {
  const [scope, setScope] = useState(createRoundScope())
  const { current: spl, setCurrent: setSpl } = usePerRoundValue('', scope)

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

          <ApplyLayerField />
          <RoundScopeThreeField
            name='batch-spl-round'
            value={scope}
            onChange={setScope}
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              toast.success(`批量操作执行成功（更新 ${count} 个）`)
              onOpenChange(false)
            }}
          >
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
