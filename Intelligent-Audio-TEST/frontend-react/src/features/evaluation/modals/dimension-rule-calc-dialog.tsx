/**
 * 评估维度页规则试算弹窗（features/evaluation/modals；11_用例域.md §4.1 操作列「规则试算」）。
 * Dialog sm:max-w-md：输入测试值（number，占位「如：96.5」）→ 主钮「试算」→
 * 结果「评分 {score} 分」+ 命中的规则行（condition/value/score 三字段高亮），
 * 规则按序匹配命中首条即停（POST /evaluation/dimensions/{id}/calculate，门槛 dim_manage）。
 */
import { Calculator } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
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
import { Label } from '@/components/ui/label'
import type { Dimension } from '@/domain/models/evaluationDimension'
import type { UseMutationResult } from '@tanstack/react-query'

type CalculateMutation = UseMutationResult<
  {
    score: number
    matchedRule: { condition: string; value: number; score: number } | null
  },
  unknown,
  { dimension: Dimension; value: number }
>

export function RuleCalcDialog({
  open,
  onOpenChange,
  dimension,
  calculate,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  dimension: Dimension | null
  calculate: CalculateMutation
}) {
  const [value, setValue] = useState('')

  const handleCalc = () => {
    const num = Number(value)
    if (!dimension || Number.isNaN(num)) return
    calculate.mutate({ dimension, value: num })
  }

  const matched = calculate.data?.matchedRule ?? null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <Calculator aria-hidden='true' className='size-4' />
            规则试算
          </DialogTitle>
          <DialogDescription>
            输入结果测试值，按维度评分规则顺序匹配计算得分
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-1.5'>
          <Label htmlFor='calc-value'>测试值</Label>
          <Input
            id='calc-value'
            type='number'
            step='any'
            placeholder='如：96.5'
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCalc()
            }}
          />
        </div>

        {calculate.data && (
          <div className='space-y-2 rounded-lg border p-3'>
            <p className='text-lg font-semibold tabular-nums'>
              评分 {calculate.data.score} 分
            </p>
            {matched ? (
              <div className='flex flex-wrap items-center gap-2'>
                <span className='text-muted-foreground text-xs'>命中规则：</span>
                <Badge variant='outline' className='gap-1 px-1.5 text-xs font-normal'>
                  结果 {matched.condition} {matched.value}
                </Badge>
                <Badge variant='secondary' className='px-1.5 text-xs font-normal'>
                  → {matched.score} 分
                </Badge>
              </div>
            ) : (
              <p className='text-muted-foreground text-xs'>
                没有规则命中（得分 0 分）
              </p>
            )}
          </div>
        )}

        {calculate.isError && (
          <p className='text-destructive text-xs'>试算失败，请重试</p>
        )}

        <DialogFooter>
          <Button
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={calculate.isPending}
          >
            关闭
          </Button>
          <Button
            onClick={handleCalc}
            disabled={!value || calculate.isPending}
          >
            {calculate.isPending ? '试算中…' : '试算'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
