/**
 * 批量设置评估维度弹窗（11_用例域.md §5.3.5，Dialog sm:max-w-3xl；标题按负责人口径与产品全域「评估维度」对齐）。
 * 轮次范围三档「所有轮次（统一设置）/指定轮次（统一设置）/逐轮设置（每轮可不同）」：
 * 「指定轮次」展开轮次号 Checkbox 组「第{n}轮」（与 §5.3.1~5.3.4 同口径）；逐轮模式轮次 Tab
 * 交互体系（§5.3.5 ②：Tab 角标=该轮已选维度数、× 关闭至少保留 1 轮、末尾「+ 添加轮次」、
 * 最后一轮 Tab 语义 -1）+ 快捷操作工具栏三件（§5.3.5 ③：从其他轮次复制 / 清空当前轮次 /
 * 应用到所有轮次）。
 * 维度选择用 DimensionPicker（V9.7.10 主/子分组云 + 分类分组：主维度分组 + 子维度归属其下、
 * 搜索命中子维度带出父维度上下文、主维度勾选联动全部子维度、孤儿子维度兜底；categories 传入时
 * 按分类聚合组头——负责人 2026-10-19「评估维度已经分组/分类了」口径）；已选维度参数卡（权重 0-100 默认 50
 * + 阈值 0-100 默认 80，DimensionParamCard 共用）；多轮整体评估维度节（跨轮次聚合勾选 + 权重/阈值
 * 配置，不选即清空——§5.3.5 数据契约 multiDimensions）。
 * 数据契约：统一模式 dimensions=[{id,name,weight,threshold}] + roundMode(all/specific) +
 * roundNumbers(specific)；逐轮模式 round_dimensions={轮次:[…],'-1':[…]}(JSON key 全字符串)；
 * 多轮整体 multi_dimensions 恒提交（空数组=清空整体评估维度）。
 */
import { Copy, Plus, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import {
  DimensionParamCard,
  type DimensionParamValue,
} from '@/features/testcases/modals/round-config/dimension-param-card'
import { DimensionPicker } from '@/features/testcases/modals/round-config/dimension-picker'
import {
  batchTestcaseAction,
  type TestcaseRoundMode,
} from '@/infrastructure/api/testcases-batch-api'

type RoundMode = 'all' | 'specific' | 'per_round'

/** 轮次键：数字轮号或最后一轮 -1（§5.3.5 ④ 语义；历史配置兼容） */
type RoundKey = number | -1

/** 逐轮 Tab 初值：按选中用例实际轮次 1..N 展开（N=0 时为空态，不编造轮次） */
const roundKeysOf = (roundCount: number): number[] =>
  Array.from({ length: roundCount }, (_, i) => i + 1)

const defaultParam = (): DimensionParamValue => ({ weight: 50, threshold: 80 })

export function BatchDimensionsDialog({
  open,
  onOpenChange,
  count,
  ids,
  roundCount,
  dimensions,
  categories = [],
  algorithmType,
  testType,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
  /** 选中用例实际轮次数（config.rounds 派生；0=空态） */
  roundCount: number
  dimensions: Dimension[]
  categories?: EvaluationCategory[]
  algorithmType?: string | null
  testType?: string | null
}) {
  const [roundMode, setRoundMode] = useState<RoundMode>('all')
  const [rounds, setRounds] = useState<RoundKey[]>(() => roundKeysOf(roundCount))
  const [activeRound, setActiveRound] = useState<RoundKey>(1)
  const [selected, setSelected] = useState<Record<RoundKey, number[]>>({})
  /** 每轮次已选维度的权重/阈值参数（§5.3.5 已选维度参数卡） */
  const [params, setParams] = useState<Record<RoundKey, Record<number, DimensionParamValue>>>({})
  /** 多轮整体评估维度（跨轮次聚合勾选 + 权重/阈值配置，不选即清空） */
  const [multiSelected, setMultiSelected] = useState<number[]>([])
  const [multiParams, setMultiParams] = useState<Record<number, DimensionParamValue>>({})
  const [submitting, setSubmitting] = useState(false)
  /** 「指定轮次」勾选的轮次号（§5.3.5 与 §5.3.1~5.3.4 同口径） */
  const [specificRounds, setSpecificRounds] = useState<number[]>(() =>
    roundCount > 0 ? [1] : []
  )
  /** 逐轮快捷操作：从其他轮次复制（Popover）+ 清空/应用到所有轮次（ConfirmDialog） */
  const [copyOpen, setCopyOpen] = useState(false)
  const [copySource, setCopySource] = useState<RoundKey>(1)
  const [confirmAction, setConfirmAction] = useState<null | 'clear' | 'applyAll'>(null)

  const roundLabels = (key: RoundKey) => (key === -1 ? '最后一轮' : `第 ${key} 轮`)

  /** 可新增的轮次号：实际轮次范围内尚未作为 Tab 打开的轮次（无则禁用「添加轮次」） */
  const nextRound = (() => {
    for (let r = 1; r <= roundCount; r++) {
      if (!rounds.includes(r)) return r
    }
    return null
  })()

  const toggleRound = (key: RoundKey, closed: boolean) => {
    setRounds((prev) => {
      const next = prev.filter((r) => r !== key)
      return closed && next.length === 0 ? [1] : next
    })
    setActiveRound((prevActive) => (prevActive === key ? rounds.find((r) => r !== key) ?? 1 : prevActive))
    setSelected((prev) => {
      const { [key]: _removed, ...rest } = prev
      return rest
    })
    setParams((prev) => {
      const { [key]: _removed, ...rest } = prev
      return rest
    })
  }

  /** 当前模式下勾选网格实际作用的轮次集合 */
  const gridKeys: RoundKey[] =
    roundMode === 'all' ? rounds : roundMode === 'specific' ? specificRounds : [activeRound]

  /** 传给 DimensionPicker 的已选集合（gridKeys 并集，主维度联动子维度） */
  const gridSelected = useMemo(
    () => [...new Set(gridKeys.flatMap((k) => selected[k] ?? []))],
    [gridKeys, selected]
  )

  /** DimensionPicker 勾选（含主维度联动子维度）应用到 gridKeys 各轮次，并初始化/清理参数 */
  const handleDimensionToggle = (ids: number[], checked: boolean) => {
    setSelected((prev) => {
      const next = { ...prev }
      gridKeys.forEach((k) => {
        const current = next[k] ?? []
        next[k] = checked
          ? [...new Set([...current, ...ids])]
          : current.filter((id) => !ids.includes(id))
      })
      return next
    })
    setParams((prev) => {
      const next = { ...prev }
      gridKeys.forEach((k) => {
        const current = { ...(next[k] ?? {}) }
        for (const id of ids) {
          if (checked && !current[id]) current[id] = defaultParam()
          if (!checked) delete current[id]
        }
        next[k] = current
      })
      return next
    })
  }

  const toggleSpecificRound = (round: number) => {
    setSpecificRounds((prev) =>
      prev.includes(round) ? prev.filter((r) => r !== round) : [...prev, round]
    )
  }

  /** 维度 id → { id, name } 配置项（提交载荷；后端 schema List[Dict[str, Any]]） */
  const dimNameMap = useMemo(
    () => new Map(dimensions.map((d) => [Number(d.id), d.name])),
    [dimensions]
  )

  /** 读取某 id 在目标轮次集合上的有效参数（未显式配置回退默认 50/80） */
  const getEffectiveParam = (id: number, keys: RoundKey[]): DimensionParamValue => {
    for (const k of keys) {
      const v = params[k]?.[id]
      if (v) return v
    }
    return defaultParam()
  }

  /** 统一/逐轮已选维度的展示参数（per_round 取当前轮，否则取 gridKeys 首个生效值） */
  const visibleSelected = roundMode === 'per_round' ? selected[activeRound] ?? [] : gridSelected
  const visibleParam = (id: number) =>
    roundMode === 'per_round'
      ? getEffectiveParam(id, [activeRound])
      : getEffectiveParam(id, gridKeys)

  const handleParamChange = (id: number, patch: Partial<DimensionParamValue>) => {
    setParams((prev) => {
      const next = { ...prev }
      gridKeys.forEach((k) => {
        next[k] = {
          ...(next[k] ?? {}),
          [id]: { ...(next[k]?.[id] ?? defaultParam()), ...patch },
        }
      })
      return next
    })
  }

  /** 多轮整体评估维度勾选（主维度联动子维度由 DimensionPicker 传入 ids） */
  const handleMultiToggle = (ids: number[], checked: boolean) => {
    setMultiSelected((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => (checked ? next.add(id) : next.delete(id)))
      return [...next]
    })
    setMultiParams((prev) => {
      const next = { ...prev }
      for (const id of ids) {
        if (checked && !next[id]) next[id] = defaultParam()
        if (!checked) delete next[id]
      }
      return next
    })
  }

  /** 逐轮快捷操作 */
  const doCopyFromRound = () => {
    setSelected((prev) => ({ ...prev, [activeRound]: [...(prev[copySource] ?? [])] }))
    setParams((prev) => ({
      ...prev,
      [activeRound]: { ...(prev[copySource] ?? {}) },
    }))
    setCopyOpen(false)
  }
  const clearRound = () => {
    setSelected((prev) => ({ ...prev, [activeRound]: [] }))
    setParams((prev) => ({ ...prev, [activeRound]: {} }))
    setConfirmAction(null)
  }
  const applyToAllRounds = () => {
    const source = selected[activeRound] ?? []
    const sourceParams = params[activeRound] ?? {}
    setSelected((prev) => {
      const next = { ...prev }
      rounds.forEach((r) => {
        if (r === activeRound) return
        next[r] = [...source]
      })
      return next
    })
    setParams((prev) => {
      const next = { ...prev }
      rounds.forEach((r) => {
        if (r === activeRound) return
        next[r] = { ...sourceParams }
      })
      return next
    })
    setConfirmAction(null)
  }

  /** 提交载荷：统一/逐轮均恒带 multiDimensions（空数组=清空整体评估维度） */
  const toDimConfig = (id: number, keys: RoundKey[]) => ({
    id,
    name: dimNameMap.get(Number(id)) ?? `dim-${id}`,
    ...getEffectiveParam(id, keys),
  })

  const handleSubmit = async () => {
    if (roundCount === 0) {
      toast.error('所选用例暂无可配置的轮次信息，无法设置评估维度')
      return
    }
    setSubmitting(true)
    try {
      const multiDimensions = multiSelected.map((id) => ({
        id,
        name: dimNameMap.get(Number(id)) ?? `dim-${id}`,
        ...(multiParams[id] ?? defaultParam()),
      }))
      if (roundMode === 'per_round') {
        const roundDimensions: Record<string, unknown[]> = {}
        for (const key of rounds) {
          roundDimensions[String(key)] = (selected[key] ?? []).map((id) => toDimConfig(id, [key]))
        }
        await batchTestcaseAction('update_dimensions', ids, {
          dimensions: [],
          testType: testType ?? '',
          roundMode: 'per_round',
          roundNumbers: [],
          roundDimensions,
          multiDimensions,
        })
      } else {
        const idsToApply = roundMode === 'specific' ? specificRounds : rounds
        const flat = [...new Set(idsToApply.flatMap((k) => selected[k] ?? []))]
        await batchTestcaseAction('update_dimensions', ids, {
          dimensions: flat.map((id) => toDimConfig(id, gridKeys)),
          testType: testType ?? '',
          roundMode: roundMode as TestcaseRoundMode,
          roundNumbers: roundMode === 'specific' ? specificRounds : undefined,
          multiDimensions,
        })
      }
      toast.success(`批量操作执行成功（更新 ${count} 个）`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量设置评估维度失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>批量设置评估维度</DialogTitle>
          <DialogDescription>您勾选了 {count} 个用例，将为其设置评估维度</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 轮次范围三档 */}
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-dim-round-mode'
                checked={roundMode === 'all'}
                onChange={() => setRoundMode('all')}
              />
              所有轮次（统一设置）
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-dim-round-mode'
                checked={roundMode === 'specific'}
                onChange={() => setRoundMode('specific')}
              />
              指定轮次（统一设置）
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-dim-round-mode'
                checked={roundMode === 'per_round'}
                onChange={() => setRoundMode('per_round')}
              />
              逐轮设置（每轮可不同）
            </label>
          </div>

          {/* 指定轮次：轮次号 Checkbox 组（§5.3.5 与 §5.3.1~5.3.4 RoundScopeField 同口径；按实际轮次） */}
          {roundMode === 'specific' && (
            <div className='space-y-1.5'>
              <span className='text-sm font-medium'>指定轮次</span>
              <div className='border-border/60 flex flex-wrap gap-1.5 rounded-lg border p-2'>
                {roundCount === 0 ? (
                  <span className='text-muted-foreground text-xs'>
                    所选用例暂无可配置的轮次信息
                  </span>
                ) : (
                  roundKeysOf(roundCount).map((round) => (
                    <label
                      key={round}
                      className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
                    >
                      <Checkbox
                        checked={specificRounds.includes(round)}
                        onCheckedChange={() => toggleSpecificRound(round)}
                      />
                      第{round}轮
                    </label>
                  ))
                )}
              </div>
            </div>
          )}

          {/* 逐轮模式轮次 Tab（§5.3.5 ②；按选中用例实际轮次渲染）+ 快捷操作工具栏（§5.3.5 ③） */}
          {roundMode === 'per_round' &&
            (roundCount === 0 ? (
              <div className='border-border/60 rounded-lg border border-dashed px-3 py-4 text-center'>
                <p className='text-muted-foreground text-sm'>
                  所选用例暂无可配置的轮次信息
                </p>
              </div>
            ) : (
            <div className='space-y-1.5'>
              <div className='border-border/60 flex flex-wrap items-center gap-1.5 rounded-lg border p-2'>
                {rounds.map((key) => {
                  const countSelected = selected[key]?.length ?? 0
                  return (
                    <span
                      key={key}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-sm transition-colors',
                        activeRound === key
                          ? 'bg-primary/10 border-primary/40 text-foreground'
                          : 'hover:bg-accent'
                      )}
                    >
                      <button
                        type='button'
                        className='font-medium'
                        onClick={() => setActiveRound(key)}
                      >
                        {roundLabels(key)}
                      </button>
                      {countSelected > 0 && (
                        <Badge className='rounded-sm px-1 font-mono text-[10px] tabular-nums'>
                          {countSelected}
                        </Badge>
                      )}
                      <button
                        type='button'
                        aria-label={`关闭 ${roundLabels(key)}`}
                        className='text-muted-foreground hover:text-destructive'
                        onClick={() => toggleRound(key, true)}
                      >
                        <X aria-hidden='true' className='size-3.5' />
                      </button>
                    </span>
                  )
                })}
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  className='h-7 gap-1'
                  disabled={nextRound === null}
                  onClick={() =>
                    setRounds((prev) =>
                      nextRound === null ? prev : [...prev, nextRound].sort((a, b) => a - b)
                    )
                  }
                >
                  <Plus aria-hidden='true' className='size-3.5' />
                  添加轮次
                </Button>
              </div>

              {/* 快捷操作工具栏三件（§5.3.5 ③） */}
              <div className='flex flex-wrap items-center gap-2'>
                <Popover
                  open={copyOpen}
                  onOpenChange={(open) => {
                    // 打开即把源默认为首个其他轮次（逐轮默认第 1 轮时不再是「复制到自身」）
                    if (open) {
                      const otherRounds = rounds.filter((r) => r !== activeRound)
                      if (otherRounds.length > 0) setCopySource(otherRounds[0])
                    }
                    setCopyOpen(open)
                  }}
                >
                  <PopoverTrigger
                    render={
                      <Button
                        type='button'
                        variant='outline'
                        size='sm'
                        disabled={rounds.length <= 1}
                      >
                        <Copy aria-hidden='true' className='size-3.5' />
                        从其他轮次复制
                      </Button>
                    }
                  />
                  <PopoverContent
                    data-testid='batch-dim-copy-source'
                    className='w-64'
                    align='start'
                  >
                    <div className='space-y-2'>
                      <div className='flex items-center gap-2'>
                        <Label className='shrink-0 text-sm'>从</Label>
                        <Select
                          value={String(copySource)}
                          onValueChange={(v) => setCopySource(Number(v) as RoundKey)}
                        >
                          <SelectTrigger size='sm' className='h-8'>
                            {/* 直接渲染轮次标签：列表未展开时 base-ui Value 只解析已挂载项，避免显示裸值 */}
                            <SelectValue>{roundLabels(copySource)}</SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            {rounds
                              .filter((r) => r !== activeRound)
                              .map((r) => (
                                <SelectItem key={r} value={String(r)}>
                                  {roundLabels(r)}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                        <Label className='shrink-0 text-sm'>复制到{roundLabels(activeRound)}</Label>
                      </div>
                      <div className='flex justify-end gap-2'>
                        <Button type='button' variant='outline' size='sm' onClick={() => setCopyOpen(false)}>
                          取消
                        </Button>
                        <Button type='button' size='sm' onClick={doCopyFromRound}>
                          确定
                        </Button>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>

                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  disabled={(selected[activeRound]?.length ?? 0) === 0}
                  onClick={() => setConfirmAction('clear')}
                >
                  <Trash2 aria-hidden='true' className='size-3.5' />
                  清空当前轮次
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  disabled={
                    (selected[activeRound]?.length ?? 0) === 0 || rounds.length <= 1
                  }
                  onClick={() => setConfirmAction('applyAll')}
                >
                  应用到所有轮次
                </Button>
              </div>
            </div>
            ))}

          {/* 维度选择（DimensionPicker 主/子分组云，参考 V9.7.10 DimensionCloud） */}
          <div>
            <p className='text-muted-foreground mb-2 text-xs'>
              {roundMode === 'per_round'
                ? '已按当前算法过滤可用维度；未选维度的轮次将被清空'
                : '已按当前算法过滤可用维度；不选任何维度点确定即清除所选轮次的评估维度'}
            </p>
            <div
              data-testid='batch-dim-round-cloud'
              className='max-h-72 overflow-y-auto rounded-lg border p-2'
            >
              <DimensionPicker
                dimensions={dimensions}
                categories={categories}
                algorithmType={algorithmType}
                selected={gridSelected}
                onToggle={handleDimensionToggle}
                showSearch
              />
            </div>
          </div>

          {/* 已选维度参数卡（权重 0-100 默认 50 + 阈值 0-100 默认 80） */}
          {visibleSelected.length > 0 ? (
            <div className='space-y-2'>
              <span className='text-sm font-medium'>维度权重和阈值配置</span>
              {visibleSelected.map((id) => {
                const dim = dimensions.find((d) => Number(d.id) === Number(id))
                if (!dim) return null
                return (
                  <DimensionParamCard
                    key={id}
                    dimension={dim}
                    params={visibleParam(id)}
                    onChange={(patch) => handleParamChange(id, patch)}
                    onRemove={() => handleDimensionToggle([id], false)}
                  />
                )
              })}
            </div>
          ) : (
            <p className='text-muted-foreground/70 text-xs'>
              未选择评估维度——不选任何维度点确定即清除所选轮次的评估维度
            </p>
          )}

          {/* 多轮整体评估维度节（§5.3.5：跨轮次聚合勾选 + 权重/阈值配置，不选即清空） */}
          <div className='border-border/60 space-y-2 rounded-lg border p-3'>
            <div className='flex flex-wrap items-center gap-2'>
              <span className='text-sm font-medium'>多轮整体评估维度（跨轮次聚合）</span>
              <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                可选
              </Badge>
            </div>
            <p className='text-muted-foreground text-xs leading-relaxed'>
              这些维度在所有轮次执行完成后触发，基于全量多轮数据计算跨轮次综合指标（如多轮平均
              WER、对话连贯性），与单轮维度独立配置。不选任何维度将清空已有的整体评估维度。
            </p>
            <div data-testid='batch-dim-multi-cloud'>
              <DimensionPicker
                dimensions={dimensions}
                categories={categories}
                algorithmType={algorithmType}
                selected={multiSelected}
                onToggle={handleMultiToggle}
                showSearch={false}
              />
            </div>
            {multiSelected.length > 0 && (
              <div className='space-y-2'>
                <span className='text-sm font-medium'>整体评估 - 权重和阈值配置</span>
                {multiSelected.map((id) => {
                  const dim = dimensions.find((d) => Number(d.id) === Number(id))
                  if (!dim) return null
                  return (
                    <DimensionParamCard
                      key={id}
                      dimension={dim}
                      params={multiParams[id] ?? defaultParam()}
                      onChange={(patch) =>
                        setMultiParams((prev) => ({
                          ...prev,
                          [id]: { ...(prev[id] ?? defaultParam()), ...patch },
                        }))
                      }
                      onRemove={() => handleMultiToggle([id], false)}
                    />
                  )
                })}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || roundCount === 0}>
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>

        {/* 逐轮快捷操作确认（§5.3.5 ③ ConfirmDialog） */}
        <ConfirmDialog
          open={confirmAction === 'clear'}
          onOpenChange={(o) => !o && setConfirmAction(null)}
          title={`确定清空${roundLabels(activeRound)}的评估维度？`}
          desc='清空后该轮次的已选评估维度与权重/阈值配置将被移除，无法撤销。'
          confirmText='确定清空'
          destructive
          handleConfirm={clearRound}
        />
        <ConfirmDialog
          open={confirmAction === 'applyAll'}
          onOpenChange={(o) => !o && setConfirmAction(null)}
          title={`将${roundLabels(activeRound)}的维度配置应用到所有其他轮次？`}
          desc='其他轮次的评估维度与权重/阈值配置将被覆盖为当前轮次的内容。'
          confirmText='确定应用'
          handleConfirm={applyToAllRounds}
        />
      </DialogContent>
    </Dialog>
  )
}
