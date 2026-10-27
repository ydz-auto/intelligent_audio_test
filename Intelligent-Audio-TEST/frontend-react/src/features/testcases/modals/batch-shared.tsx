/**
 * 批量弹窗共享片段（11_用例域.md §5.3 九件套统一口径）。
 * 轮次范围（RadioGroup「所有轮次/指定轮次」→ 指定轮次展开轮次号 Checkbox 组「第{n}轮」）
 * + 应用层级多选（目标人音频/全局背景噪声/轮次背景噪声/干扰人/声纹，§5.3.2~5.3.4 同口径）。
 * RoundScopeThreeField 为三档轮次范围（所有轮次统一/指定轮次统一/逐轮设置每轮可不同，§5.3.5 口径），
 * 供 §5.3.1~5.3.5 全部轮次级批量弹窗共用（负责人反馈「其他批量操作也是三档轮次范围逐项可用」）。
 * 内部受控状态随弹窗重新挂载即重置；数据契约 roundMode/rounds/appliedLayers 留接线批次。
 */
import { useCallback, useState, type ReactNode } from 'react'

import { Checkbox } from '@/components/ui/checkbox'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export type RoundScopeMode = 'all' | 'specific'

export function RoundScopeField({
  name,
  roundCount,
  unknownRoundCount = 0,
}: {
  /** radio name（同页多弹窗实例隔离，防表单串扰） */
  name: string
  /** 轮次数（按选中用例真实轮次，多选取最大轮次；0=无可配置轮次，给空态——INT-1731/INT-1506） */
  roundCount: number
  /** 选中用例中轮次未知（列表尚未加载）的条数；>0 时不得当成「无轮次」（INT-1506） */
  unknownRoundCount?: number
}) {
  const [mode, setMode] = useState<RoundScopeMode>('all')
  const [selected, setSelected] = useState<number[]>([])

  const toggleRound = (round: number) => {
    setSelected((prev) =>
      prev.includes(round) ? prev.filter((r) => r !== round) : [...prev, round]
    )
  }

  return (
    <div className='space-y-2'>
      <span className='text-sm font-medium'>轮次范围</span>
      <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
        <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
          <input
            type='radio'
            name={name}
            checked={mode === 'all'}
            onChange={() => setMode('all')}
          />
          所有轮次
        </label>
        <label
          className={cn(
            'hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm',
            roundCount === 0 && 'cursor-not-allowed opacity-50'
          )}
        >
          <input
            type='radio'
            name={name}
            disabled={roundCount === 0}
            checked={mode === 'specific'}
            onChange={() => setMode('specific')}
          />
          指定轮次
        </label>
      </div>
      {mode === 'specific' && (
        <div className='border-border/60 flex flex-wrap gap-1.5 rounded-lg border p-2'>
          {roundCount === 0 ? (
            <span className='text-muted-foreground text-xs'>
              {unknownRoundCount > 0
                ? `其中 ${unknownRoundCount} 个用例的轮次信息尚未加载，无法指定轮次`
                : '所选用例暂无可配置的轮次信息'}
            </span>
          ) : (
            roundNumbers(roundCount).map((round) => (
              <label
                key={round}
                className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
              >
                <Checkbox
                  checked={selected.includes(round)}
                  onCheckedChange={() => toggleRound(round)}
                />
                第{round}轮
              </label>
            ))
          )}
        </div>
      )}
    </div>
  )
}

/** 三档轮次范围值（§5.3.5 口径；rounds 为逐轮模式轮次 Tab 集） */
export type RoundScopeThreeMode = 'all' | 'specific' | 'per_round'

export interface RoundScopeThreeValue {
  mode: RoundScopeThreeMode
  /** 指定轮次勾选的轮次号 */
  specificRounds: number[]
  /** 逐轮模式轮次 Tab（第1~N 轮；按选中用例真实轮次） */
  rounds: number[]
  /** 逐轮模式当前编辑轮次 */
  activeRound: number
}

/** 轮次号候选（1..N；N = 选中用例真实轮次数，多选取最大轮次，未知回落 1——INT-1731） */
export function roundNumbers(total: number): number[] {
  return Array.from({ length: Math.max(1, total) }, (_, i) => i + 1)
}

/** 勾选轮次收敛到真实存在的轮次（不存在轮次不得提交，否则后端静默回成功不生效——INT-1731） */
export function existingRounds(rounds: number[], total: number): number[] {
  const max = Math.max(1, total)
  return [...new Set(rounds.filter((r) => Number.isInteger(r) && r >= 1 && r <= max))].sort(
    (a, b) => a - b
  )
}

/** 三档轮次范围初值（rounds 按选中用例实际轮次数 1..N 展开；0=空态，不编造轮次——INT-1506） */
export function createRoundScope(roundCount = 1): RoundScopeThreeValue {
  return {
    mode: 'all',
    specificRounds: roundCount > 0 ? [1] : [],
    rounds: roundCount > 0 ? roundNumbers(roundCount) : [],
    activeRound: 1,
  }
}

/** 三档轮次范围选择器（§5.3.5；供 §5.3.1~5.3.5 全部轮次级批量弹窗共用） */
export function RoundScopeThreeField({
  name,
  value,
  onChange,
  roundCount,
  unknownRoundCount = 0,
  renderTabIndicator,
  disabledModes = [],
  disabledHint,
}: {
  name: string
  value: RoundScopeThreeValue
  onChange: (next: RoundScopeThreeValue) => void
  /** 轮次数（按选中用例真实轮次，多选取最大轮次；0=无可配置轮次，给空态——INT-1731/INT-1506） */
  roundCount: number
  /** 选中用例中轮次未知（列表尚未加载）的条数；>0 时不得当成「无轮次」（INT-1506） */
  unknownRoundCount?: number
  /**
   * 逐轮 Tab 角标插槽（§5.7.1 上传选项共用件：维度段=该轮已选维度数、设备段=已选对勾）。
   * 可选；现有调用方不传 = 保持原渲染（零回归）。
   */
  renderTabIndicator?: (round: number) => ReactNode
  /** 禁用档（§5.7.2：上传窗 N=1 时「指定轮次」「逐轮设置」禁用）；不传 = 三档全可用 */
  disabledModes?: RoundScopeThreeMode[]
  /** 禁用档 hover 提示文案（§9 文案表） */
  disabledHint?: string
}) {
  const hasRounds = roundCount > 0
  const roundEmptyText =
    unknownRoundCount > 0
      ? `其中 ${unknownRoundCount} 个用例的轮次信息尚未加载，无法按轮次设置`
      : '所选用例暂无可配置的轮次信息'
  const setMode = (mode: RoundScopeThreeMode) => onChange({ ...value, mode })
  const toggleSpecificRound = (round: number) =>
    onChange({
      ...value,
      specificRounds: value.specificRounds.includes(round)
        ? value.specificRounds.filter((r) => r !== round)
        : [...value.specificRounds, round],
    })

  /** 单档 radio；禁用档（调用方指定或轮次未知）加 cursor-not-allowed/opacity-50，并外包 Tooltip（桌面 hover 文案） */
  const renderModeOption = (mode: RoundScopeThreeMode, label: string) => {
    const disabled = disabledModes.includes(mode) || (mode !== 'all' && !hasRounds)
    const option = (
      <label
        className={cn(
          'hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm',
          disabled && 'cursor-not-allowed opacity-50 hover:bg-transparent'
        )}
      >
        <input
          type='radio'
          name={name}
          checked={value.mode === mode}
          disabled={disabled}
          onChange={() => setMode(mode)}
        />
        {label}
      </label>
    )
    if (!disabled || !disabledHint) return option
    return (
      <TooltipProvider delay={0}>
        <Tooltip>
          <TooltipTrigger render={option} />
          <TooltipContent className='max-w-72 text-xs'>{disabledHint}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <div className='space-y-2'>
      <span className='text-sm font-medium'>轮次范围</span>
      <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
        {renderModeOption('all', '所有轮次（统一设置）')}
        {renderModeOption('specific', '指定轮次（统一设置）')}
        {renderModeOption('per_round', '逐轮设置（每轮可不同）')}
      </div>

      {value.mode === 'specific' && (
        <div
          data-testid={`${name}-specific-rounds`}
          className='border-border/60 flex flex-wrap gap-1.5 rounded-lg border p-2'
        >
          {!hasRounds ? (
            <span className='text-muted-foreground text-xs'>{roundEmptyText}</span>
          ) : (
            roundNumbers(roundCount).map((round) => (
              <label
                key={round}
                className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
              >
                <Checkbox
                  checked={value.specificRounds.includes(round)}
                  onCheckedChange={() => toggleSpecificRound(round)}
                />
                第{round}轮
              </label>
            ))
          )}
        </div>
      )}

      {value.mode === 'per_round' && (
        <div className='border-border/60 flex flex-wrap items-center gap-1.5 rounded-lg border p-2'>
          {!hasRounds ? (
            <span className='text-muted-foreground text-xs'>{roundEmptyText}</span>
          ) : (
            value.rounds.map((round) => (
              <button
                key={round}
                type='button'
                onClick={() => onChange({ ...value, activeRound: round })}
                className={cn(
                  'inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-sm transition-colors',
                  value.activeRound === round
                    ? 'bg-primary/10 border-primary/40 text-foreground font-medium'
                    : 'hover:bg-accent text-muted-foreground'
                )}
              >
                第{round}轮
                {renderTabIndicator?.(round)}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

/**
 * 逐轮/统一值绑定（§5.3.1~5.3.4 三档轮次范围共用）：
 * 所有轮次/指定轮次 → 单一值；逐轮设置 → 按当前轮次 Tab 分轮存值。
 */
export function usePerRoundValue<V>(initial: V, scope: RoundScopeThreeValue) {
  const [uniform, setUniform] = useState<V>(initial)
  const [perRound, setPerRound] = useState<Record<number, V>>({})
  const current =
    scope.mode === 'per_round'
      ? (perRound[scope.activeRound] ?? uniform)
      : uniform
  const setCurrent = useCallback(
    (v: V) => {
      if (scope.mode === 'per_round') {
        setPerRound((prev) => ({ ...prev, [scope.activeRound]: v }))
      } else {
        setUniform(v)
      }
    },
    [scope.mode, scope.activeRound]
  )
  /** 整体重置（算法切换等场景：清空统一值与逐轮值，回退默认） */
  const resetValue = useCallback(() => {
    setUniform(initial)
    setPerRound({})
  }, [initial])
  /**
   * perRound：逐轮设置模式各轮已编辑值（key 为轮次号，仅含用户实际改过的轮次；
   * 未覆盖的轮次提交时不出现在 round_values，后端按「未指定轮次保留原配置」处理）。
   */
  return { current, setCurrent, resetValue, perRound }
}

/** 应用层级五项（§5.3.2~5.3.4；noise 弹窗默认勾选 全局/轮次背景噪声；INT-1970 返工 P3 改名：
 *  case级→全局、segment级→轮次，仅展示文案，wire targets 不变） */
export const APPLY_LAYERS = [
  { id: 'target', label: '目标人音频' },
  { id: 'case-bg', label: '全局背景噪声' },
  { id: 'segment-bg', label: '轮次背景噪声' },
  { id: 'interferer', label: '干扰人' },
  { id: 'voiceprint', label: '声纹' },
] as const

export type ApplyLayerId = (typeof APPLY_LAYERS)[number]['id']

/** 应用层级 id → 批量接口 targets 取值（Vue 基准：target→audio / case-bg→caseBackgroundNoise / …） */
export const APPLY_LAYER_TARGET_MAP: Record<ApplyLayerId, string> = {
  target: 'audio',
  'case-bg': 'caseBackgroundNoise',
  'segment-bg': 'segmentBackgroundNoise',
  interferer: 'interferer',
  voiceprint: 'voiceprint',
}

/** 应用层级 id 集合 → 批量接口 targets 数组（按 APPLY_LAYERS 顺序） */
export function applyLayerToTargets(layers: Iterable<ApplyLayerId>): string[] {
  const set = new Set(layers)
  return APPLY_LAYERS.filter((l) => set.has(l.id)).map((l) => APPLY_LAYER_TARGET_MAP[l.id])
}

export function ApplyLayerField({
  defaultChecked = [],
  value,
  onChange,
  hint = '可多选；留空表示不应用任何层级',
}: {
  /** 默认勾选的层级 id（§5.3.4 默认 全局/轮次背景噪声） */
  defaultChecked?: ApplyLayerId[]
  /** 受控模式（INT-710 接线：提交时读取勾选层级） */
  value?: ApplyLayerId[]
  onChange?: (next: ApplyLayerId[]) => void
  /** 提示文案（各批量操作留空回退口径不同：声压/设备→目标人音频，噪声→全局/轮次背景噪声） */
  hint?: string
}) {
  const [internal, setInternal] = useState<Set<string>>(
    () => new Set(defaultChecked)
  )
  const checkedSet = value ? new Set(value) : internal

  const toggle = (id: string) => {
    const next = new Set(checkedSet)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    if (value !== undefined && onChange) {
      onChange(APPLY_LAYERS.filter((l) => next.has(l.id)).map((l) => l.id))
    } else {
      setInternal(next)
    }
  }

  return (
    <div className='space-y-2'>
      <span className='text-sm font-medium'>应用层级</span>
      <div className='flex flex-wrap gap-1.5'>
        {APPLY_LAYERS.map((layer) => (
          <label
            key={layer.id}
            className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
          >
            <Checkbox
              checked={checkedSet.has(layer.id)}
              onCheckedChange={() => toggle(layer.id)}
            />
            {layer.label}
          </label>
        ))}
      </div>
      <p className='text-muted-foreground/70 text-xs'>{hint}</p>
    </div>
  )
}
