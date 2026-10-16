/**
 * 批量设置评价维度弹窗（11_用例域.md §5.3.5，Dialog sm:max-w-3xl）。
 * 轮次范围三档「所有轮次（统一设置）/指定轮次（统一设置）/逐轮设置（每轮可不同）」；
 * 逐轮模式轮次 Tab 交互体系（§5.3.5 ②：Tab 角标=该轮已选维度数、× 关闭至少保留 1 轮、
 * 末尾「+ 添加轮次」、最后一轮 Tab 语义 -1）+ 维度勾选网格（按当前算法过滤）。
 * 可视稿演示态：提交走 toast；数据契约 roundMode/roundDimensions 序列化留接线批次。
 */
import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'

type RoundMode = 'all' | 'specific' | 'per_round'

/** 轮次键：数字轮号或最后一轮 -1（§5.3.5 ④ 语义） */
type RoundKey = number | -1

export function BatchDimensionsDialog({
  open,
  onOpenChange,
  count,
  dimensions,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  dimensions: EvaluationDimensionItem[]
}) {
  const [roundMode, setRoundMode] = useState<RoundMode>('all')
  const [rounds, setRounds] = useState<RoundKey[]>([1, 2, -1])
  const [activeRound, setActiveRound] = useState<RoundKey>(1)
  const [selected, setSelected] = useState<Record<RoundKey, number[]>>({})

  const roundLabels = (key: RoundKey) => (key === -1 ? '最后一轮' : `第 ${key} 轮`)

  const toggleRound = (key: RoundKey, closed: boolean) => {
    setRounds((prev) => {
      const next = prev.filter((r) => r !== key)
      return closed && next.length === 0 ? [1] : next
    })
    setActiveRound((prevActive) => (prevActive === key ? rounds.find((r) => r !== key) ?? 1 : prevActive))
    setSelected((prev) => {
      const { [key]: _removed, ...rest } = prev
      return rest
    })
  }

  const mainDimensions = dimensions.filter((d) => d.dimensionType !== 'sub')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>批量设置评价维度</DialogTitle>
          <DialogDescription>您勾选了 {count} 个用例，将为其设置评价维度</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 轮次范围三档 */}
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-dim-round-mode'
                checked={roundMode === 'all'}
                onChange={() => setRoundMode('all')}
              />
              所有轮次（统一设置）
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-dim-round-mode'
                checked={roundMode === 'specific'}
                onChange={() => setRoundMode('specific')}
              />
              指定轮次（统一设置）
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-dim-round-mode'
                checked={roundMode === 'per_round'}
                onChange={() => setRoundMode('per_round')}
              />
              逐轮设置（每轮可不同）
            </label>
          </div>

          {/* 逐轮模式轮次 Tab（§5.3.5 ②） */}
          {roundMode === 'per_round' && (
            <div className='border-border/60 flex flex-wrap items-center gap-1.5 rounded-lg border p-2'>
              {rounds.map((key) => {
                const countSelected = selected[key]?.length ?? 0
                return (
                  <span
                    key={key}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-sm transition-colors',
                      activeRound === key
                        ? 'bg-primary/10 border-primary/40 text-foreground'
                        : 'hover:bg-accent'
                    )}
                  >
                    <button
                      type='button'
                      className='font-medium'
                      onClick={() => setActiveRound(key)}
                    >
                      {roundLabels(key)}
                    </button>
                    {countSelected > 0 && (
                      <Badge className='rounded-sm px-1 font-mono text-[10px] tabular-nums'>
                        {countSelected}
                      </Badge>
                    )}
                    <button
                      type='button'
                      aria-label={`关闭 ${roundLabels(key)}`}
                      className='text-muted-foreground hover:text-destructive'
                      onClick={() => toggleRound(key, true)}
                    >
                      <X aria-hidden='true' className='size-3.5' />
                    </button>
                  </span>
                )
              })}
              <Button
                type='button'
                variant='ghost'
                size='sm'
                className='h-7 gap-1'
                onClick={() => setRounds((prev) => [...prev, Math.max(...prev.filter((r) => r !== -1), 0) + 1])}
              >
                <Plus aria-hidden='true' className='size-3.5' />
                添加轮次
              </Button>
            </div>
          )}

          {/* 维度勾选网格 */}
          <div>
            <p className='text-muted-foreground mb-2 text-xs'>
              已按当前算法过滤可用维度；不选任何维度点确定即清除所选轮次的评估维度
            </p>
            <div className='grid max-h-56 grid-cols-2 gap-1.5 overflow-y-auto sm:grid-cols-3'>
              {mainDimensions.map((dim) => (
                <label
                  key={dim.id}
                  className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-sm transition-colors'
                >
                  <Checkbox
                    checked={(selected[activeRound] ?? []).includes(dim.id)}
                    onCheckedChange={() => {
                      const current = selected[activeRound] ?? []
                      setSelected((prev) => ({
                        ...prev,
                        [activeRound]: current.includes(dim.id)
                          ? current.filter((id) => id !== dim.id)
                          : [...current, dim.id],
                      }))
                    }}
                  />
                  <span className='truncate'>{dim.name}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              toast.success('批量操作执行成功（更新全部选中用例）')
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
