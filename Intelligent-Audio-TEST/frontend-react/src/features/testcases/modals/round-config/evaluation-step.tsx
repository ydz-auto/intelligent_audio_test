/**
 * 轮次步骤④：评估维度（11_用例域.md §5.1）。
 * 维度 chips 多选区（按当前算法过滤可用维度，过滤时提示条）+ 已选维度参数卡
 * （每维度：权重 1-10 Slider + 阈值 Input + LLM Judge 时 模型/Prompt 模板/最大 Token/Temperature 字段卡）。
 */
import { SlidersHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'
import { getAlgorithmLabel } from '@/features/testcases/constants'

/** mock LLM Judge 判定（接线后按 DimensionItem.resultType === 'llm_judge' 实测） */
const LLM_JUDGE_DIMENSION_IDS = new Set([2])

/** 各算法的可用维度过滤（mock 演示；接线后按算法-维度关联表实测） */
const ALGO_DIMENSION_FILTER: Record<string, number[]> = {
  'asr-v3': [1, 2],
  'asr-stream': [3, 4],
  'eval-ensemble': [1, 2, 3, 4],
}

export function EvaluationStep({
  dimensions,
  algorithmType,
}: {
  dimensions: EvaluationDimensionItem[]
  algorithmType?: string | null
}) {
  const available = useMemo(() => {
    const filter = algorithmType ? (ALGO_DIMENSION_FILTER[algorithmType] ?? null) : null
    const main = dimensions.filter((d) => d.dimensionType !== 'sub')
    return filter ? main.filter((d) => filter.includes(d.id)) : main
  }, [dimensions, algorithmType])

  const [selected, setSelected] = useState<number[]>([1])

  const toggle = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const dimensionOf = (id: number) => dimensions.find((d) => d.id === id)

  return (
    <div className='space-y-3'>
      {algorithmType && (
        <p className='rounded-md bg-muted/60 px-2 py-1.5 text-xs'>
          已根据算法类型「{getAlgorithmLabel(algorithmType)}」过滤可用维度
        </p>
      )}
      <div className='flex flex-wrap gap-1.5'>
        {available.map((d) => {
          const checked = selected.includes(d.id)
          return (
            <button
              key={d.id}
              type='button'
              onClick={() => toggle(d.id)}
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                checked
                  ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                  : 'hover:bg-accent border-border'
              )}
              aria-pressed={checked}
            >
              {d.name}
            </button>
          )
        })}
        {available.length === 0 && (
          <p className='text-muted-foreground text-sm'>该算法下暂无可用评估维度</p>
        )}
      </div>

      {selected.length === 0 ? (
        <p className='text-muted-foreground py-4 text-center text-sm'>
          未选择评估维度——不选任何维度点保存即清除当前轮次的评估维度
        </p>
      ) : (
        selected.map((id) => {
          const dim = dimensionOf(id)
          const llmJudge = LLM_JUDGE_DIMENSION_IDS.has(id)
          return (
            <div key={id} className='bg-background ring-foreground/10 rounded-lg p-3 ring-1'>
              <div className='flex items-center gap-2'>
                <SlidersHorizontal aria-hidden='true' className='text-muted-foreground size-4' />
                <span className='text-sm font-medium'>{dim?.name ?? `维度 #${id}`}</span>
                {llmJudge && (
                  <Badge variant='outline' className='gap-1 rounded-md px-1.5 text-[11px]'>
                    LLM Judge
                  </Badge>
                )}
                <Button
                  type='button'
                  variant='ghost'
                  size='icon-sm'
                  aria-label={`移除维度 ${dim?.name ?? id}`}
                  className='hover:text-destructive ms-auto size-7'
                  onClick={() => toggle(id)}
                >
                  ✕
                </Button>
              </div>
              <div className='mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2'>
                <div className='space-y-2'>
                  <div className='flex items-center justify-between'>
                    <Label className='text-sm'>权重（1-10）</Label>
                    <span className='font-mono text-xs tabular-nums'>{dim?.weight ?? 5}</span>
                  </div>
                  <Slider
                    defaultValue={[dim?.weight ?? 5]}
                    min={1}
                    max={10}
                    step={1}
                    aria-label={`${dim?.name ?? id} 权重`}
                  />
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>阈值</Label>
                  <Input type='number' defaultValue={0.6} min={0} max={1} step={0.05} className='h-8' />
                </div>
              </div>
              {llmJudge && (
                <div className='mt-3 grid gap-x-6 gap-y-3 border-t pt-3 sm:grid-cols-2'>
                  <div className='space-y-1.5'>
                    <Label className='text-sm'>模型</Label>
                    <Input defaultValue='claude-sonnet-5-5' className='h-8' />
                  </div>
                  <div className='space-y-1.5'>
                    <Label className='text-sm'>最大 Token 数</Label>
                    <Input type='number' defaultValue={1024} min={1} max={8192} className='h-8' />
                  </div>
                  <div className='space-y-1.5 sm:col-span-2'>
                    <Label className='text-sm'>Prompt 模板</Label>
                    <Textarea
                      rows={2}
                      defaultValue='请根据 {{asr_result}} 与参考文本 {{asr_ref}} 评估语义理解正确性，返回 0-100 分。'
                      className='font-mono text-xs'
                    />
                  </div>
                  <div className='space-y-1.5'>
                    <Label className='text-sm'>Temperature</Label>
                    <Input type='number' defaultValue={0.7} min={0} max={2} step={0.1} className='h-8' />
                  </div>
                </div>
              )}
            </div>
          )
        })
      )}
    </div>
  )
}
