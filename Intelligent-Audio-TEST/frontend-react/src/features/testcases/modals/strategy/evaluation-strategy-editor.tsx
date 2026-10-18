/**
 * 评估策略折叠节（11_用例域.md §5.1.3，INT-592 核心：评估配置抽为可复用「评估策略」引用）。
 * 默认收起；节头「评估策略」+ 状态徽章（未配置 / 已引用「{名}」/ 已引用并覆盖 {n} 项）+ ChevronDown。
 * 展开态三模式 RadioGroup：不使用评估策略 / 引用已有策略（Select 带摘要 + 策略摘要卡 + 用例级覆盖区
 * 两枚 Switch）/ 新建策略（内联表单 POST 入库后进入 Select 全局可复用）。
 * 内嵌 OverallEvaluationEditor/GlobalNoiseEditor 为策略字段编辑器（原两常驻节移入，抽屉瘦身一半）。
 * 向后兼容：存量 config.dimensions/background_noise 直载（无 strategy_id）→ 映射「新建策略」模式并提示。
 * 用例承载契约 config.evaluationStrategy（见 domain/models/evaluationStrategy）；onChange 输出
 * EvaluationStrategyEditorValue（mode/strategyId/overrides/inline*），序列化落在抽屉保存侧。
 */
import { ChevronDown, CircleAlert, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
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
import { GlobalNoiseEditor } from '@/features/testcases/modals/round-config/global-noise-editor'
import { OverallEvaluationEditor } from '@/features/testcases/modals/round-config/overall-evaluation-editor'

export type EvaluationStrategyMode = 'none' | 'reference' | 'create'

/** 评估策略节输出值（抽屉保存侧序列化为 config.evaluationStrategy + 存量直载字段） */
export interface EvaluationStrategyEditorValue {
  mode: EvaluationStrategyMode
  /** 引用态策略 id（mode=reference） */
  strategyId?: string | null
  /** 用例级覆盖（仅覆盖字段；引用+覆盖语义） */
  overrides?: CaseEvaluationStrategy['overrides']
  /** 内联态（mode=create 未存为策略）：映射 config.dimensions / config.background_noise 直载 */
  inlineDimensions?: TestCaseDimensionItem[]
  inlineBackgroundNoise?: TestCaseBackgroundNoiseItem | null
}

/**
 * 评估策略节值 → 用例保存载荷序列化（§5.1.3 用例承载契约）。
 * - none：清空 evaluationStrategy 与存量直载字段；
 * - reference：{ strategy_id, overrides? }（仅覆盖字段；引用无覆盖则 overrides 缺省）；
 * - create（内联未存为策略）：config.dimensions / config.background_noise 直载（无 strategy_id，
 *   等价内联策略、执行口径不变——向后兼容）。
 */
export function serializeEvaluationStrategy(
  value: EvaluationStrategyEditorValue | null
): {
  evaluationStrategy: CaseEvaluationStrategy | null
  dimensions: TestCaseDimensionItem[]
  backgroundNoise: TestCaseBackgroundNoiseItem | null
} {
  if (!value || value.mode === 'none') {
    return { evaluationStrategy: null, dimensions: [], backgroundNoise: null }
  }
  if (value.mode === 'reference') {
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
  return {
    evaluationStrategy: null,
    dimensions: value.inlineDimensions ?? [],
    backgroundNoise: value.inlineBackgroundNoise ?? null,
  }
}

export function EvaluationStrategyEditor({
  initialValue,
  legacyDimensions,
  legacyBackgroundNoise,
  dimensions,
  algorithmType,
  onChange,
}: {
  /** 编辑态 config.evaluationStrategy（无 strategyId 的存量用例缺省） */
  initialValue?: CaseEvaluationStrategy | null
  /** 存量用例 config.dimensions 直载（向后兼容；无 strategy_id 时等价内联策略） */
  legacyDimensions?: TestCaseDimensionItem[]
  /** 存量用例 config.background_noise 直载 */
  legacyBackgroundNoise?: TestCaseBackgroundNoiseItem | null
  dimensions: Dimension[]
  algorithmType?: string | null
  onChange: (next: EvaluationStrategyEditorValue) => void
}) {
  const strategiesQuery = useEvaluationStrategies()
  const createStrategy = useCreateEvaluationStrategy()
  const strategies = strategiesQuery.data ?? []

  const [expanded, setExpanded] = useState(false)
  const [mode, setMode] = useState<EvaluationStrategyMode>(() =>
    initialValue?.strategyId
      ? 'reference'
      : (legacyDimensions?.length ?? 0) > 0 || legacyBackgroundNoise != null
        ? 'create'
        : 'none'
  )
  const [strategyId, setStrategyId] = useState<string | null>(
    initialValue?.strategyId ?? null
  )
  const [overrides, setOverrides] = useState<CaseEvaluationStrategy['overrides']>(
    initialValue?.overrides ?? null
  )
  const [inlineDimensions, setInlineDimensions] = useState<TestCaseDimensionItem[]>(
    legacyDimensions ?? []
  )
  const [inlineBackgroundNoise, setInlineBackgroundNoise] =
    useState<TestCaseBackgroundNoiseItem | null>(legacyBackgroundNoise ?? null)
  const [createName, setCreateName] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [createSaving, setCreateSaving] = useState(false)

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
      setOverrides((prev) => ({
        ...prev,
        dimensions: selectedStrategy
          ? selectedStrategy.dimensions.map((d) => ({ ...d, llmJudgeConfig: d.llmJudgeConfig ? { ...d.llmJudgeConfig } : undefined }))
          : [],
      }))
    } else {
      setOverrides((prev) => {
        const next = { ...(prev ?? {}) }
        delete next.dimensions
        return { ...next, dimensions: undefined }
      })
    }
  }

  const handleToggleOverrideBackgroundNoise = (checked: boolean) => {
    if (checked) {
      setOverrides((prev) => ({
        ...prev,
        backgroundNoise: selectedStrategy?.backgroundNoise
          ? { ...selectedStrategy.backgroundNoise }
          : null,
      }))
    } else {
      setOverrides((prev) => {
        const next = { ...(prev ?? {}) }
        next.backgroundNoise = undefined
        return next
      })
    }
  }

  /** 名称全局唯一校验（对照现有策略；新建/内联共用） */
  const nameDuplicate = useMemo(
    () => strategies.some((s) => s.name === createName.trim()),
    [strategies, createName]
  )

  /** 新建策略内联表单 → POST 入库 → 引用新策略（进入 Select 全局可复用） */
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
        dimensions: inlineDimensions,
        backgroundNoise: inlineBackgroundNoise,
      })
      toast.success(`策略「${created.name}」已保存并引用`)
      setMode('reference')
      setStrategyId(String(created.id))
      setOverrides(null)
      setCreateName('')
      setCreateDescription('')
      setInlineDimensions([])
      setInlineBackgroundNoise(null)
    } catch {
      toast.error('策略保存失败')
    } finally {
      setCreateSaving(false)
    }
  }

  /** 状态 → onChange 输出（引用/覆盖变更即时反映——跨组件状态同步点①） */
  useEffect(() => {
    onChange({
      mode,
      strategyId: mode === 'reference' ? strategyId : null,
      overrides: mode === 'reference' ? overrides : null,
      inlineDimensions: mode === 'create' ? inlineDimensions : undefined,
      inlineBackgroundNoise: mode === 'create' ? inlineBackgroundNoise : undefined,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, strategyId, overrides, inlineDimensions, inlineBackgroundNoise])

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
            整体评估维度与全局背景噪声可抽为可复用「评估策略」，由多组用例共享；简单用例可跳过本配置，
            保存后不执行整体评估、不播放全局噪声。
          </p>

          {/* 模式三选 */}
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='evaluation-strategy-mode'
                checked={mode === 'none'}
                onChange={() => {
                  setMode('none')
                  setStrategyId(null)
                  setOverrides(null)
                }}
              />
              不使用评估策略
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='evaluation-strategy-mode'
                checked={mode === 'reference'}
                onChange={() => setMode('reference')}
              />
              引用已有策略
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='evaluation-strategy-mode'
                checked={mode === 'create'}
                onChange={() => setMode('create')}
              />
              新建策略
            </label>
          </div>

          {/* 不使用 */}
          {mode === 'none' && (
            <p className='text-muted-foreground py-2 text-xs'>
              简单用例可跳过本配置，保存后不执行整体评估、不播放全局噪声。
            </p>
          )}

          {/* 引用已有策略 */}
          {mode === 'reference' && (
            <div className='space-y-3'>
              <div className='space-y-1.5'>
                <Label className='text-sm'>选择策略</Label>
                <Select value={strategyId ?? ''} onValueChange={(v) => setStrategyId(v ?? null)}>
                  <SelectTrigger size='sm' className='h-8 w-full sm:max-w-md'>
                    <SelectValue placeholder='请选择要引用的评估策略' />
                  </SelectTrigger>
                  <SelectContent>
                    {strategies.length === 0 ? (
                      <div className='text-muted-foreground px-3 py-2 text-sm'>
                        暂无可用策略，点击下方「新建策略」创建
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

              {/* 用例级覆盖区 */}
              {selectedStrategy && (
                <div className='space-y-2'>
                  <p className='text-muted-foreground text-xs'>用例级覆盖（默认跟随策略配置）</p>
                  <div className='flex items-center justify-between gap-2'>
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
                  </div>
                  {overrides?.dimensions != null && (
                    <div className='border-border/60 rounded-lg border p-3'>
                      <OverallEvaluationEditor
                        dimensions={dimensions}
                        algorithmType={algorithmType}
                        value={overrides.dimensions}
                        onChange={(next) =>
                          setOverrides((prev) => ({ ...(prev ?? {}), dimensions: next }))
                        }
                      />
                    </div>
                  )}

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
                  {overrides?.backgroundNoise != null && (
                    <div className='border-border/60 rounded-lg border p-3'>
                      <GlobalNoiseEditor
                        value={overrides.backgroundNoise}
                        onChange={(next) =>
                          setOverrides((prev) => ({
                            ...(prev ?? {}),
                            backgroundNoise: next ?? undefined,
                          }))
                        }
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 新建策略（内联表单；存量用例直载也映射到此模式） */}
          {mode === 'create' && (
            <div className='space-y-3'>
              {(legacyDimensions?.length ?? 0) > 0 || legacyBackgroundNoise != null ? (
                <div className='flex items-start gap-2 rounded-lg border border-dashed p-2 text-xs'>
                  <CircleAlert aria-hidden='true' className='text-info mt-0.5 size-3.5 shrink-0' />
                  <p className='text-muted-foreground'>
                    检测到存量用例的内联评估配置，已映射为「新建策略」模式；点击下方
                    「保存策略并引用」可另存为复用策略。
                  </p>
                </div>
              ) : (
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
              )}

              <div className='border-border/60 rounded-lg border p-3'>
                <OverallEvaluationEditor
                  dimensions={dimensions}
                  algorithmType={algorithmType}
                  value={inlineDimensions}
                  onChange={setInlineDimensions}
                />
              </div>

              <div className='border-border/60 rounded-lg border p-3'>
                <GlobalNoiseEditor
                  value={inlineBackgroundNoise}
                  onChange={setInlineBackgroundNoise}
                />
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
