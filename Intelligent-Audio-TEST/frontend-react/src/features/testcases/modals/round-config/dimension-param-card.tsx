/**
 * 已选维度参数卡（用例编辑抽屉 §5.1 / §5.1.2 共用）。
 * 每维度：名称 + LLM Judge 徽章 + 移除钮；权重 number 0-100 默认 50 + 阈值 number 0-100 默认 80
 * （非 LLM Judge）；LLM Judge 时 模型 + Prompt 模板（自由文本，默认值取维度自身配置）。
 * 模型/Prompt 后端没有可枚举的选项接口（`GET /algorithm/options` 只下发算法类型，不含
 * LLM 模型），因此不渲染写死的下拉选项、也不写死默认模型：默认值读维度配置
 * `dimension.llmJudgeConfig`（§5.5 维度表单同源字段），用户在此可覆盖，未改动不写入 case config。
 * 数据契约 config.dimensions 项 = { id, name, weight, threshold, (llmJudgeConfig: {model, promptTemplate}) }
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
  model?: string
  promptTemplate?: string
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
  const llmJudge = dimension.resultType === 'llm_judge'
  /** 默认值回退维度自身 LLM Judge 配置（维度配置接口下发；未配置即空，不注入占位模型） */
  const model = params.model ?? dimension.llmJudgeConfig?.model ?? ''
  const promptTemplate =
    params.promptTemplate ?? dimension.llmJudgeConfig?.promptTemplate ?? ''

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
        {!llmJudge ? (
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
        ) : (
          <>
            <div className='space-y-1.5'>
              <Label htmlFor={`dim-model-${dimension.id}`} className='text-sm'>
                模型
              </Label>
              <Input
                id={`dim-model-${dimension.id}`}
                value={model}
                placeholder='如：gpt-4o-mini'
                onChange={(e) => onChange({ model: e.target.value })}
                className='h-8'
              />
            </div>
            <div className='space-y-1.5 sm:col-span-2'>
              <Label htmlFor={`dim-prompt-${dimension.id}`} className='text-sm'>
                Prompt 模板
              </Label>
              <Input
                id={`dim-prompt-${dimension.id}`}
                value={promptTemplate}
                placeholder='可使用 {{asr_result}} {{asr_ref}} 等变量'
                onChange={(e) => onChange({ promptTemplate: e.target.value })}
                className='h-8'
              />
            </div>
            <p className='text-muted-foreground/70 text-xs sm:col-span-2'>
              默认取该维度定义中的 LLM Judge 配置，留空表示沿用维度定义。
            </p>
          </>
        )}
      </div>
    </div>
  )
}
