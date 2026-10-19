/**
 * 整体评估维度编辑器（11_用例域.md §5.1.3.1 评估策略字段，原 §5.1.2 常驻节移入）。
 * 受控组件（value/onChange），作策略字段编辑器由评估策略节引用复用——不再是用例常驻节。
 * 节头「整体评估维度」+ 徽章「所有轮次」+ 副标题 + 描述文案（逐字平移）；启用整体评估 Switch
 * （默认开；已有维度数据时自动启用；关闭即清空维度数组 emit 空数组）；维度多选用 DimensionPicker
 * （V9.7.10 主/子分组云 + 分类分组：主维度「主」徽章/子维度「子」徽章，勾主联动子；
 * categories 传入时按分类聚合组头）；已选维度参数卡（权重 0-100 默认 50
 * + 阈值 0-100 默认 80 非 LLM Judge；LLM Judge 时 模型 Select + Prompt 模板 Select）。
 * 数据契约 config.dimensions = [{ id, name, weight, threshold, (llmJudgeConfig: {model, promptTemplate}) }]
 * ——TestCaseDimensionItem {id,name,weight,threshold,test_type}（schemas/testcase.py:85-90）；
 * 触发条件=顶层数组非空；报告取值整体优先、无整体结果取各轮算术平均。
 */
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import type { TestCaseDimensionItem } from '@/domain/models/evaluationStrategy'
import {
  DimensionParamCard,
  type DimensionParamValue,
} from '@/features/testcases/modals/round-config/dimension-param-card'
import { DimensionPicker } from '@/features/testcases/modals/round-config/dimension-picker'

const defaultParams = (): DimensionParamValue => ({
  weight: 50,
  threshold: 80,
})

export function OverallEvaluationEditor({
  dimensions,
  categories = [],
  algorithmType,
  value,
  onChange,
}: {
  dimensions: Dimension[]
  categories?: EvaluationCategory[]
  algorithmType?: string | null
  /** 维度配置值（整体评估维度数组；空=未启用） */
  value: TestCaseDimensionItem[]
  onChange: (next: TestCaseDimensionItem[]) => void
}) {
  const [enabled, setEnabled] = useState(value.length > 0)

  const dimensionOf = (id: number) => dimensions.find((d) => Number(d.id) === id)
  const itemOf = (id: number) => value.find((v) => Number(v.id) === id)
  const selected = value.map((v) => Number(v.id))

  const handleToggle = (ids: number[], checked: boolean) => {
    const next = new Set(value.map((v) => Number(v.id)))
    ids.forEach((id) => {
      if (checked) next.add(id)
      else next.delete(id)
    })
    const list = dimensions
      .filter((d) => next.has(Number(d.id)))
      .map((d) => {
        const existing = itemOf(Number(d.id))
        if (existing) return existing
        const llmJudge = d.resultType === 'llm_judge'
        return {
          id: d.id,
          name: d.name,
          weight: defaultParams().weight,
          threshold: defaultParams().threshold,
          ...(llmJudge
            ? { llmJudgeConfig: { model: 'claude-3-sonnet', promptTemplate: 'default' } }
            : {}),
        }
      })
    onChange(list)
  }

  const handleRemove = (id: number) =>
    onChange(value.filter((v) => Number(v.id) !== id))

  const handleParamChange = (id: number, patch: Partial<DimensionParamValue>) =>
    onChange(
      value.map((v) =>
        Number(v.id) === id
          ? {
              ...v,
              weight: patch.weight ?? v.weight,
              threshold: patch.threshold ?? v.threshold,
              ...(patch.model || patch.promptTemplate
                ? {
                    llmJudgeConfig: {
                      model: patch.model ?? v.llmJudgeConfig?.model ?? 'claude-3-sonnet',
                      promptTemplate:
                        patch.promptTemplate ?? v.llmJudgeConfig?.promptTemplate ?? 'default',
                    },
                  }
                : v.llmJudgeConfig
                  ? { llmJudgeConfig: v.llmJudgeConfig }
                  : {}),
            }
          : v
      )
    )

  return (
    <div className='space-y-2'>
      {/* 节头：标题 + 「所有轮次」徽章 + 副标题 */}
      <div className='flex flex-wrap items-center gap-2'>
        <h4 className='text-sm font-medium'>整体评估维度</h4>
        <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
          所有轮次
        </Badge>
      </div>
      <p className='text-muted-foreground text-xs leading-relaxed'>
        整体评估在所有轮次执行完成后触发，将多轮结果汇总后统一送给评估端点。与单轮评估
        （每轮独立打分）不同，整体评估关注的是跨轮次的综合指标，例如多轮平均 WER、对话连贯性、
        上下文一致性等。若评估端点支持逐轮计算，整体评估会随结果返回各轮得分并覆盖单轮评估的
        对应轮次记录，保证整体与逐轮口径一致。
      </p>

      {/* 启用整体评估 */}
      <div className='flex items-center gap-2'>
        <Switch
          checked={enabled}
          onCheckedChange={(v) => {
            setEnabled(v)
            if (!v) onChange([])
          }}
          aria-label='启用整体评估'
          id='overall-evaluation-enabled'
        />
        <Label htmlFor='overall-evaluation-enabled' className='text-sm font-normal'>
          启用整体评估
        </Label>
      </div>

      {enabled && (
        <>
          <DimensionPicker
            dimensions={dimensions}
            categories={categories}
            algorithmType={algorithmType}
            selected={selected}
            onToggle={handleToggle}
          />
          {value.length === 0 ? (
            <p className='text-muted-foreground py-3 text-center text-sm'>
              未选择评估维度——不选任何维度点保存即清除整体评估维度
            </p>
          ) : (
            <div className='space-y-2'>
              {value.map((item) => {
                const dim = dimensionOf(Number(item.id))
                const label = dim?.name ?? item.name
                if (!dim) {
                  // 策略字段可能引用已下架维度：按名称占位渲染（不崩坏编辑器）
                  return (
                    <div key={String(item.id)} className='bg-background ring-foreground/10 rounded-lg p-3 ring-1'>
                      <div className='flex items-center gap-2'>
                        <span className='text-sm font-medium'>{label}</span>
                        <ButtonGhostRemove onRemove={() => handleRemove(Number(item.id))} />
                      </div>
                    </div>
                  )
                }
                return (
                  <DimensionParamCard
                    key={String(item.id)}
                    dimension={dim}
                    params={{
                      weight: item.weight,
                      threshold: item.threshold,
                      model: item.llmJudgeConfig?.model,
                      promptTemplate: item.llmJudgeConfig?.promptTemplate,
                    }}
                    onChange={(patch) => handleParamChange(Number(item.id), patch)}
                    onRemove={() => handleRemove(Number(item.id))}
                  />
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** 占位移除钮（无维度对象时仍可移除） */
function ButtonGhostRemove({ onRemove }: { onRemove: () => void }) {
  return (
    <button
      type='button'
      aria-label='移除维度'
      className='hover:text-destructive ms-auto size-7'
      onClick={onRemove}
    >
      ✕
    </button>
  )
}
