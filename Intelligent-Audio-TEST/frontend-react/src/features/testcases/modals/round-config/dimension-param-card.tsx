/**
 * 已选维度参数卡（用例编辑抽屉 §5.1 / §5.1.2 共用）。
 * 每维度：名称 + LLM Judge 只读徽章 + 移除钮；权重 number 0-100 默认 50 + 阈值 number 0-100 默认 80
 * （非 LLM Judge）。
 * LLM Judge 由维度自身 task_type_code 表达（后端派生 llm_judge），不是结果类型，
 * 也没有模型 / Prompt 模板可选项（INT-1671 裁定 A 撤除）。
 * 数据契约 config.dimensions 项 = { id, name, weight, threshold }。提交时按字段覆盖
 * （EvaluationStrategyMergeService 只覆盖 weight / threshold / llmJudgeConfig），
 * 因此历史条目上已有的 llmJudgeConfig 不会被这两个字段的提交清掉，原样透传。
 */
import { SlidersHorizontal } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { Dimension } from '@/domain/models/evaluationDimension'

export interface DimensionParamValue {
  weight: number
  threshold: number
}

export function DimensionParamCard({
  dimension,
  params,
  onChange,
  onRemove,
}: {
  dimension: Dimension
  params: DimensionParamValue
  onChange: (patch: Partial<DimensionParamValue>) => void
  onRemove: () => void
}) {
  const llmJudge = dimension.llmJudge === true

  return (
    <div className='bg-background ring-foreground/10 rounded-lg p-3 ring-1'>
      <div className='flex items-center gap-2'>
        <SlidersHorizontal aria-hidden='true' className='text-muted-foreground size-4' />
        <span className='text-sm font-medium'>{dimension.name}</span>
        {llmJudge && (
          <Badge variant='outline' className='gap-1 rounded-md px-1.5 text-[11px]'>
            LLM Judge
          </Badge>
        )}
        <Button
          type='button'
          variant='ghost'
          size='icon-sm'
          aria-label={`移除维度 ${dimension.name}`}
          className='hover:text-destructive ms-auto size-7'
          onClick={onRemove}
        >
          ✕
        </Button>
      </div>
      <div className='mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label className='text-sm'>权重</Label>
          <Input
            type='number'
            min={0}
            max={100}
            step={1}
            value={params.weight}
            onChange={(e) => onChange({ weight: Number(e.target.value) })}
            className='h-8'
          />
        </div>
        {!llmJudge && (
          <div className='space-y-1.5'>
            <Label className='text-sm'>阈值</Label>
            <Input
              type='number'
              min={0}
              max={100}
              step={1}
              value={params.threshold}
              onChange={(e) => onChange({ threshold: Number(e.target.value) })}
              className='h-8'
            />
          </div>
        )}
      </div>
    </div>
  )
}
