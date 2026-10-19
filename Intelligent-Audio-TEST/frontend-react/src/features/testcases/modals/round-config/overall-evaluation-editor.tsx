/**
 * 整体评估维度节（11_用例域.md §5.1.2 常驻节，case 级 config.dimensions）。
 * V9.7.10 OverallEvaluationEditor 逐字平移换壳。
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
}: {
  dimensions: Dimension[]
  categories?: EvaluationCategory[]
  algorithmType?: string | null
}) {
  const [enabled, setEnabled] = useState(true)
  const [selected, setSelected] = useState<number[]>([1, 11])
  const [params, setParams] = useState<Record<number, DimensionParamValue>>({
    1: { weight: 50, threshold: 80 },
    11: { weight: 50, threshold: 80 },
  })

  const dimensionOf = (id: number) => dimensions.find((d) => d.id === id)

  const handleToggle = (ids: number[], checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => (checked ? next.add(id) : next.delete(id)))
      const list = [...next]
      setParams((p) => {
        const merged = { ...p }
        for (const id of ids) {
          if (checked && !merged[id]) merged[id] = defaultParams()
        }
        return merged
      })
      return list
    })
  }

  const handleRemove = (id: number) => {
    setSelected((prev) => prev.filter((x) => x !== id))
    setParams((prev) => {
      const { [id]: _removed, ...rest } = prev
      return rest
    })
  }

  return (
    <div className='space-y-2'>
      {/* 节头：标题 + 「所有轮次」徽章 + 副标题 */}
      <div className='flex flex-wrap items-center gap-2'>
        <h4 className='text-base font-medium'>整体评估维度</h4>
        <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
          所有轮次
        </Badge>
      </div>
      <p className='font-mono text-muted-foreground text-xs'>
        config.dimensions — 对多轮测试结果的综合评估
      </p>
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
            if (!v) {
              setSelected([])
              setParams({})
            }
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
          {selected.length === 0 ? (
            <p className='text-muted-foreground py-3 text-center text-sm'>
              未选择评估维度——不选任何维度点保存即清除整体评估维度
            </p>
          ) : (
            <div className='space-y-2'>
              {selected.map((id) => {
                const dim = dimensionOf(id)
                if (!dim) return null
                return (
                  <DimensionParamCard
                    key={id}
                    dimension={dim}
                    params={params[id] ?? defaultParams()}
                    onChange={(patch) =>
                      setParams((prev) => ({
                        ...prev,
                        [id]: { ...(prev[id] ?? defaultParams()), ...patch },
                      }))
                    }
                    onRemove={() => handleRemove(id)}
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
