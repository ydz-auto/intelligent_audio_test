/**
 * 轮次步骤④：评估维度（11_用例域.md §5.1 RoundEvaluationEditor 平移）。
 * 顶部单轮描述条 + 过滤提示条（当前算法有关联维度时才显示）+ DimensionPicker（V9.7.10
 * 主/子分组云 + 分类分组：搜索+已选计数，主维度「主」徽章/子维度「子」徽章，勾主联动子；
 * categories 传入时按分类聚合组头）+ 已选维度参数卡（权重 0-100 默认 50 + 阈值 0-100 默认 80
 * 非 LLM Judge；LLM Judge 维度只读徽章，无模型 / Prompt 选项（INT-1681 裁定 A）；
 * 不含「最大 Token/Temperature」——属维度定义 §5.5）+ 底部「启用本轮评估」Checkbox。
 * 受控组件：value=RoundEvaluationDraft（enabled/selectedIds/params），onChange 回写轮次草稿，
 * 供 addRound 复制上一轮 evaluation（⚠️ 实施注意②）。
 */
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import { getAlgorithmLabel } from '@/features/testcases/constants'
import type { RoundEvaluationDraft } from '@/features/testcases/modals/round-config/round-nav'
import {
  DimensionParamCard,
  type DimensionParamValue,
} from '@/features/testcases/modals/round-config/dimension-param-card'
import { DimensionPicker } from '@/features/testcases/modals/round-config/dimension-picker'

const defaultParams = (): DimensionParamValue => ({
  weight: 50,
  threshold: 80,
})

export function EvaluationStep({
  dimensions,
  categories = [],
  algorithmType,
  algorithmLabels,
  value,
  onChange,
}: {
  dimensions: Dimension[]
  categories?: EvaluationCategory[]
  algorithmType?: string | null
  /** 算法类型码 → 中文名（真实 /algorithm/options）；缺项时提示条不写名称（不显类型码，INT-1687） */
  algorithmLabels?: Record<string, string>
  value: RoundEvaluationDraft
  onChange: (next: RoundEvaluationDraft) => void
}) {
  const dimensionOf = (id: number) => dimensions.find((d) => d.id === id)
  /** INT-1687：算法名取真实选项，未命中不回落类型码 */
  const algorithmLabel = getAlgorithmLabel(algorithmType, algorithmLabels)

  const handleToggle = (ids: number[], checked: boolean) => {
    onChange({
      ...value,
      selectedIds: (() => {
        const next = new Set(value.selectedIds)
        ids.forEach((id) => (checked ? next.add(id) : next.delete(id)))
        return [...next]
      })(),
      params: ids.reduce(
        (acc, id) => {
          if (checked && !acc[id]) acc[id] = defaultParams()
          return acc
        },
        { ...value.params }
      ),
    })
  }

  const handleRemove = (id: number) => {
    onChange({
      ...value,
      selectedIds: value.selectedIds.filter((x) => x !== id),
      params: (() => {
        const { [id]: _removed, ...rest } = value.params
        return rest
      })(),
    })
  }

  return (
    <div className='space-y-3'>
      <p className='text-muted-foreground text-xs leading-relaxed'>
        单轮评估对每一轮独立提交、独立打分；若同一维度也配置在整体评估中，整体评估返回的逐轮结果
        会覆盖对应轮次的记录。
      </p>
      {algorithmType && (
        <p className='rounded-md bg-muted/60 px-2 py-1.5 text-xs'>
          {algorithmLabel
            ? `已根据算法类型「${algorithmLabel}」过滤可用维度`
            : '已根据当前算法过滤可用维度'}
        </p>
      )}

      <DimensionPicker
        dimensions={dimensions}
        categories={categories}
        algorithmType={algorithmType}
        selected={value.selectedIds}
        onToggle={handleToggle}
      />

      {value.selectedIds.length === 0 ? (
        <p className='text-muted-foreground py-4 text-center text-sm'>
          未选择评估维度——不选任何维度点保存即清除当前轮次的评估维度
        </p>
      ) : (
        <div className='space-y-2'>
          {value.selectedIds.map((id) => {
            const dim = dimensionOf(id)
            if (!dim) return null
            return (
              <DimensionParamCard
                key={id}
                dimension={dim}
                params={value.params[id] ?? defaultParams()}
                onChange={(patch) =>
                  onChange({
                    ...value,
                    params: {
                      ...value.params,
                      [id]: { ...(value.params[id] ?? defaultParams()), ...patch },
                    },
                  })
                }
                onRemove={() => handleRemove(id)}
              />
            )
          })}
        </div>
      )}

      {/* 底部「启用本轮评估」 */}
      <div className='flex items-center gap-2 border-t pt-3'>
        <Checkbox
          checked={value.enabled}
          aria-label='启用本轮评估'
          onCheckedChange={(c) => onChange({ ...value, enabled: c })}
        />
        <Label htmlFor='round-evaluation-enabled' className='text-sm font-normal'>
          启用本轮评估
        </Label>
      </div>
    </div>
  )
}
