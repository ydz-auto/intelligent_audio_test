/**
 * 评估策略折叠节（11_用例域.md §5.1.3，INT-592 核心：评估配置抽为可复用「评估策略」引用）。
 * INT-1424（负责人口径）：全局背景噪声 / 整体评估维度恢复为用例配置独立节（case-mutate-drawer
 * 常驻渲染 OverallEvaluationEditor/GlobalNoiseEditor），本折叠节只负责「策略复用」：
 * - 不使用评估策略：用例自带内联配置（即下方两个独立节的值）；
 * - 引用已有策略：Select 带摘要 + 策略摘要卡 + 用例级覆盖两枚 Switch（覆盖值同样经
 *   两个独立节编辑——引用态下独立节显示/编辑的是覆盖值）；
 * - 新建策略：内联表单（名称/描述）POST 入库，快照两个独立节当前值，成功后进入 Select 全局可复用。
 * 数据契约 config.evaluationStrategy（见 domain/models/evaluationStrategy）；onChange 输出
 * EvaluationStrategyEditorValue（mode/strategyId/overrides），序列化落在抽屉保存侧。
 */
import { ChevronDown, CircleAlert, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { Dimension } from '@/domain/models/evaluationDimension'
import type {
  CaseEvaluationStrategy,
  TestCaseBackgroundNoiseItem,
  TestCaseDimensionItem,
} from '@/domain/models/evaluationStrategy'
import {
  useCreateEvaluationStrategy,
  useEvaluationStrategies,
} from '@/application/testcases/useEvaluationStrategies'

export type EvaluationStrategyMode = 'none' | 'reference' | 'create'

/** 评估策略节输出值（抽屉保存侧序列化；维度/噪声值存于抽屉两个独立节） */
export interface EvaluationStrategyEditorValue {
  mode: EvaluationStrategyMode
  /** 引用态策略 id（mode=reference） */
  strategyId?: string | null
  /** 用例级覆盖（引用态下独立节显示/编辑的就是覆盖值） */
  overrides?: CaseEvaluationStrategy['overrides']
}

/**
 * 评估策略节值 → 用例保存载荷序列化（§5.1.3 用例承载契约）。
 * - none / create（未保存为策略的内联态）：config.dimensions / config.background_noise
 *   直载（等价内联策略、执行口径不变——向后兼容）；
 * - reference：{ strategy_id, overrides? }（仅覆盖字段；引用无覆盖则 overrides 缺省）。
 */
export function serializeEvaluationStrategy(
  value: EvaluationStrategyEditorValue | null,
  inlineDimensions: TestCaseDimensionItem[],
  inlineBackgroundNoise: TestCaseBackgroundNoiseItem | null
): {
  evaluationStrategy: CaseEvaluationStrategy | null
  dimensions: TestCaseDimensionItem[]
  backgroundNoise: TestCaseBackgroundNoiseItem | null
} {
  if (!value || value.mode === 'none' || value.mode === 'create') {
    return {
      evaluationStrategy: null,
      dimensions: inlineDimensions,
      backgroundNoise: inlineBackgroundNoise,
    }
  }
  const overrides = value.overrides
  const hasOverrides =
    overrides != null &&
    (overrides.dimensions != null || overrides.backgroundNoise != null)
  return {
    evaluationStrategy: {
      strategyId: value.strategyId ?? null,
      ...(hasOverrides ? { overrides } : {}),
    },
    dimensions: [],
    backgroundNoise: null,
  }
}

export function EvaluationStrategyEditor({
  value,
  onChange,
  dimensions,
  currentDimensions,
  currentBackgroundNoise,
}: {
  /** 当前节值（mode/strategyId/overrides；受控组件） */
  value: EvaluationStrategyEditorValue
  onChange: (next: EvaluationStrategyEditorValue) => void
  /** 维度列表（策略摘要卡维度徽章 name 解析） */
  dimensions: Dimension[]
  /** 两个独立节当前值（新建策略保存时快照入策略） */
  currentDimensions: TestCaseDimensionItem[]
  currentBackgroundNoise: TestCaseBackgroundNoiseItem | null
}) {
  const strategiesQuery = useEvaluationStrategies()
  const createStrategy = useCreateEvaluationStrategy()
  const strategies = strategiesQuery.data ?? []

  const [expanded, setExpanded] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [createSaving, setCreateSaving] = useState(false)

  const mode = value.mode
  const strategyId = value.strategyId ?? null
  const overrides = value.overrides ?? null
  const selectedStrategy = strategies.find((s) => String(s.id) === String(strategyId)) ?? null

  /** 覆盖计数（徽章「已引用并覆盖 {n} 项」） */
  const overrideCount = (overrides?.dimensions ? 1 : 0) + (overrides?.backgroundNoise ? 1 : 0)

  /** 节头徽章（三态） */
  const badge = useMemo(() => {
    if (mode === 'reference') {
      if (selectedStrategy && overrideCount > 0) return `已引用并覆盖 ${overrideCount} 项`
      if (selectedStrategy) return `已引用「${selectedStrategy.name}」`
    }
    return '未配置'
  }, [mode, selectedStrategy, overrideCount])

  const handleToggleOverrideDimensions = (checked: boolean) => {
    if (checked) {
      // 覆盖开启：初始值=策略维度（同源；关闭覆盖时还原策略值语义）
      onChange({
        ...value,
        overrides: {
          ...(overrides ?? {}),
          dimensions: selectedStrategy
            ? selectedStrategy.dimensions.map((d) => ({
                ...d,
                llmJudgeConfig: d.llmJudgeConfig ? { ...d.llmJudgeConfig } : undefined,
              }))
            : [],
        },
      })
    } else {
      const next = { ...(overrides ?? {}) }
      next.dimensions = undefined
      onChange({ ...value, overrides: next })
    }
  }

  const handleToggleOverrideBackgroundNoise = (checked: boolean) => {
    if (checked) {
      onChange({
        ...value,
        overrides: {
          ...(overrides ?? {}),
          backgroundNoise: selectedStrategy?.backgroundNoise
            ? { ...selectedStrategy.backgroundNoise }
            : null,
        },
      })
    } else {
      const next = { ...(overrides ?? {}) }
      next.backgroundNoise = undefined
      onChange({ ...value, overrides: next })
    }
  }

  /** 名称全局唯一校验（对照现有策略；新建/内联共用） */
  const nameDuplicate = useMemo(
    () => strategies.some((s) => s.name === createName.trim()),
    [strategies, createName]
  )

  /** 新建策略：快照两个独立节当前值 POST 入库 → 引用新策略（进入 Select 全局可复用） */
  const handleSaveStrategyAndReference = async () => {
    const name = createName.trim()
    if (!name) {
      toast.error('请输入策略名称')
      return
    }
    if (nameDuplicate) {
      toast.error('策略名称已存在，请更换名称')
      return
    }
    setCreateSaving(true)
    try {
      const created = await createStrategy.mutateAsync({
        name,
        description: createDescription.trim() || null,
        dimensions: currentDimensions,
        backgroundNoise: currentBackgroundNoise,
      })
      toast.success(`策略「${created.name}」已保存并引用`)
      onChange({ mode: 'reference', strategyId: String(created.id), overrides: null })
      setCreateName('')
      setCreateDescription('')
    } catch {
      toast.error('策略保存失败')
    } finally {
      setCreateSaving(false)
    }
  }

  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      {/* 节头 */}
      <CollapsibleTrigger className='hover:bg-muted/40 flex w-full items-center gap-2 rounded-lg px-1 py-2 text-start transition-colors'>
        <span className='text-base font-medium'>评估策略</span>
        <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
          {badge}
        </Badge>
        <ChevronDown
          aria-hidden='true'
          className={cn('text-muted-foreground ms-auto size-4 transition-transform', expanded && 'rotate-180')}
        />
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className='space-y-3 border-t pt-3'>
          {/* 说明文案 */}
          <p className='text-muted-foreground text-xs leading-relaxed'>
            上方「整体评估维度 / 全局背景噪声」为本用例的独立配置；可将它们抽为可复用「评估策略」，
            由多组用例共享。引用策略后，用例级覆盖仍通过上方两个独立节编辑。
          </p>

          {/* 模式三选 */}
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='evaluation-strategy-mode'
                checked={mode === 'none'}
                onChange={() => onChange({ mode: 'none', strategyId: null, overrides: null })}
              />
              不使用评估策略
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='evaluation-strategy-mode'
                checked={mode === 'reference'}
                onChange={() => onChange({ ...value, mode: 'reference' })}
              />
              引用已有策略
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='evaluation-strategy-mode'
                checked={mode === 'create'}
                onChange={() => onChange({ mode: 'create', strategyId: null, overrides: null })}
              />
              新建策略
            </label>
          </div>

          {/* 不使用 */}
          {mode === 'none' && (
            <p className='text-muted-foreground py-2 text-xs'>
              用例使用自身内联配置（上方两个独立节）；简单用例可跳过本配置，保存后不执行整体评估、
              不播放全局噪声。
            </p>
          )}

          {/* 引用已有策略 */}
          {mode === 'reference' && (
            <div className='space-y-3'>
              <div className='space-y-1.5'>
                <Label className='text-sm'>选择策略</Label>
                <Select value={strategyId ?? ''} onValueChange={(v) => onChange({ ...value, strategyId: v ?? null })}>
                  <SelectTrigger size='sm' className='h-8 w-full sm:max-w-md'>
                    <SelectValue placeholder='请选择要引用的评估策略' />
                  </SelectTrigger>
                  <SelectContent>
                    {strategies.length === 0 ? (
                      <div className='text-muted-foreground px-3 py-2 text-sm'>
                        暂无可用策略，点击「新建策略」创建
                      </div>
                    ) : (
                      strategies.map((s) => (
                        <SelectItem key={String(s.id)} value={String(s.id)}>
                          {s.name} · 整体维度 {s.dimensions.length} 项 · 噪声{' '}
                          {s.backgroundNoise ? '已配置' : '未配置'}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </div>

              {/* 策略摘要卡 */}
              {selectedStrategy && (
                <div className='bg-background ring-foreground/10 space-y-2 rounded-lg p-3 ring-1'>
                  <div className='flex items-start justify-between gap-2'>
                    <div>
                      <p className='text-sm font-medium'>{selectedStrategy.name}</p>
                      {selectedStrategy.description && (
                        <p className='text-muted-foreground mt-0.5 text-xs'>
                          {selectedStrategy.description}
                        </p>
                      )}
                    </div>
                    <Badge variant='outline' className='rounded-md px-1.5 text-[11px]'>
                      全局策略
                    </Badge>
                  </div>
                  <div className='flex flex-wrap items-center gap-1'>
                    {selectedStrategy.dimensions.map((item) => {
                      const dim = dimensions.find((d) => Number(d.id) === Number(item.id))
                      return (
                        <Badge key={String(item.id)} variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                          {dim?.name ?? item.name}
                          {dim?.dimensionType === 'main' && <span className='ms-1 opacity-70'>主</span>}
                          {dim?.dimensionType === 'sub' && <span className='ms-1 opacity-70'>子</span>}
                        </Badge>
                      )
                    })}
                    {selectedStrategy.dimensions.length === 0 && (
                      <span className='text-muted-foreground text-xs'>无整体评估维度</span>
                    )}
                  </div>
                  {selectedStrategy.backgroundNoise ? (
                    <p className='text-muted-foreground text-xs tabular-nums'>
                      全局噪声：{selectedStrategy.backgroundNoise.audioName ?? '—'} · 声压级{' '}
                      {selectedStrategy.backgroundNoise.spl ?? 0} dB
                    </p>
                  ) : (
                    <p className='text-muted-foreground text-xs'>未配置全局背景噪声</p>
                  )}
                </div>
              )}

              {/* 用例级覆盖区（覆盖值经上方两个独立节编辑） */}
              {selectedStrategy && (
                <div className='space-y-2'>
                  <p className='text-muted-foreground text-xs'>
                    用例级覆盖（默认跟随策略配置；开启后在上方「整体评估维度 / 全局背景噪声」节中编辑覆盖值）
                  </p>
                  <div className='flex items-center gap-2'>
                    <Switch
                      checked={overrides?.dimensions != null}
                      onCheckedChange={handleToggleOverrideDimensions}
                      aria-label='覆盖整体评估维度'
                      id='override-dimensions'
                    />
                    <Label htmlFor='override-dimensions' className='text-sm font-normal'>
                      覆盖整体评估维度
                    </Label>
                  </div>
                  <div className='flex items-center gap-2'>
                    <Switch
                      checked={overrides?.backgroundNoise != null}
                      onCheckedChange={handleToggleOverrideBackgroundNoise}
                      aria-label='覆盖全局背景噪声'
                      id='override-background-noise'
                    />
                    <Label htmlFor='override-background-noise' className='text-sm font-normal'>
                      覆盖全局背景噪声
                    </Label>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 新建策略（快照两个独立节当前值入库） */}
          {mode === 'create' && (
            <div className='space-y-3'>
              {(currentDimensions.length > 0 || currentBackgroundNoise != null) && (
                <div className='flex items-start gap-2 rounded-lg border border-dashed p-2 text-xs'>
                  <CircleAlert aria-hidden='true' className='text-info mt-0.5 size-3.5 shrink-0' />
                  <p className='text-muted-foreground'>
                    将把上方「整体评估维度 / 全局背景噪声」的当前配置保存为可复用策略。
                  </p>
                </div>
              )}
              <div className='grid gap-3 sm:grid-cols-2'>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>策略名称 *</Label>
                  <Input
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    maxLength={50}
                    placeholder='请输入策略名称（最多 50 字）'
                    className='h-8'
                    aria-label='策略名称'
                  />
                  <p className='text-muted-foreground/70 text-xs tabular-nums'>
                    {createName.length}/50{nameDuplicate && <span className='text-destructive'> · 策略名称已存在</span>}
                  </p>
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-sm'>策略描述</Label>
                  <Textarea
                    value={createDescription}
                    onChange={(e) => setCreateDescription(e.target.value)}
                    rows={1}
                    placeholder='补充策略说明（可选）'
                    className='h-8 min-h-8 resize-none'
                  />
                </div>
              </div>

              <div className='flex items-center justify-end gap-2'>
                <Button
                  type='button'
                  size='sm'
                  className='h-8 gap-1.5'
                  disabled={createSaving}
                  onClick={() => void handleSaveStrategyAndReference()}
                >
                  <Sparkles aria-hidden='true' className='size-3.5' />
                  {createSaving ? '保存中…' : '保存策略并引用'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
