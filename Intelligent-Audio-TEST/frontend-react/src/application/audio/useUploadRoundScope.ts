/**
 * 上传选项轮次范围编排（application 层；§5.7.8 落位）。
 * 两段各一套三档状态（评估维度 / 播放设备，互不联动）：所有轮次统一 / 指定轮次统一 / 逐轮设置；
 * 轮次基数 N 由调用方按 §5.7.2 传入（上传窗恒 1、文件夹导入 = JSON rounds 最大轮数）。
 * 逐轮快捷操作三件（从其他轮次复制 / 清空当前轮次 / 应用到所有轮次，§5.7.1）在此编排，
 * UI 只负责确认框文案。提交计划（dimensionPlan / devicePlan）交给 infrastructure 组装 merge 载荷。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

import { useEvaluationDimensions } from '@/application/evaluation/use-dimensions'
import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  clampUploadRoundScope,
  createUploadRoundScope,
  type UploadDimensionPlan,
  type UploadDevicePlan,
  type UploadRoundScopeValue,
  type UploadRoundValueMap,
} from '@/domain/models/uploadRoundScope'
import type { UploadDimensionItem } from '@/infrastructure/api/audio-upload-api'

export interface UseUploadRoundScopeOptions {
  /** 轮次基数 N（§5.7.2；≥1） */
  roundCount: number
  /** 文件集签名：改选文件夹 / 改文件集时整体重置为默认（第 1 轮，§5.7.2） */
  resetKey?: string
}

export interface UploadRoundScopeController {
  roundCount: number
  /** 评估维度段轮次范围（受控值 + setter） */
  dimensionScope: UploadRoundScopeValue
  setDimensionScope: (next: UploadRoundScopeValue) => void
  /** 设置区当前展示的维度 id 集（逐轮档 = 当前轮；其余 = 统一值） */
  dimensionIds: number[]
  setDimensionIds: (ids: number[]) => void
  /** 某轮已选维度数（逐轮 Tab 角标，§5.7.1） */
  dimensionCountOf: (round: number) => number
  /** 播放设备段轮次范围（受控值 + setter） */
  deviceScope: UploadRoundScopeValue
  setDeviceScope: (next: UploadRoundScopeValue) => void
  /** 设置区当前展示的设备 id（字符串，'' = 未选） */
  deviceId: string
  setDeviceId: (id: string) => void
  /** 某轮是否已选设备（逐轮 Tab 角标 = 对勾，§5.7.1） */
  deviceSelectedOf: (round: number) => boolean
  /** 逐轮快捷操作三件（维度段；作用于当前轮） */
  copyDimensionFromRound: (sourceRound: number) => void
  clearDimensionRound: () => void
  applyDimensionRoundToAll: () => void
  /** 逐轮快捷操作三件（设备段；作用于当前轮） */
  copyDeviceFromRound: (sourceRound: number) => void
  clearDeviceRound: () => void
  applyDeviceRoundToAll: () => void
  /** 多轮整体评估维度（跨轮次聚合，§5.7.3） */
  multiDimensionIds: number[]
  setMultiDimensionIds: (ids: number[]) => void
  /** 单轮维度条目（含 name——§5.7.7 审计 P3-2：顶层 config.dimensions 条目必带 name） */
  dimensionItems: UploadDimensionItem[]
  /** 多轮整体维度条目（round_scope='multi'，走顶层 dimensions） */
  multiDimensionItems: UploadDimensionItem[]
  dimensionPlan: UploadDimensionPlan
  devicePlan: UploadDevicePlan
  /** 顶层 default_playback_device_id（all/specific = 统一值、per_round = 第 1 轮值，§5.7.7） */
  defaultDeviceId: number | null
}

const toDeviceId = (value: string): number | null => {
  if (!value) return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

/** 维度 id 集并集（保持出现顺序，去重） */
function unionIds(lists: number[][]): number[] {
  const seen = new Set<number>()
  const out: number[] = []
  for (const list of lists) {
    for (const id of list) {
      const numeric = Number(id)
      if (!Number.isFinite(numeric) || seen.has(numeric)) continue
      seen.add(numeric)
      out.push(numeric)
    }
  }
  return out
}

export function useUploadRoundScope({
  roundCount,
  resetKey,
}: UseUploadRoundScopeOptions): UploadRoundScopeController {
  const count = Math.max(1, Math.floor(roundCount) || 1)

  // 维度条目元数据（name / weight）来自真实 /evaluation/dimensions（与 UploadOptions 共用 query 缓存）
  const dimensionsQuery = useEvaluationDimensions()
  const catalog: Dimension[] = dimensionsQuery.data ?? []

  const [dimensionScope, setDimensionScopeState] = useState(createUploadRoundScope)
  const [deviceScope, setDeviceScopeState] = useState(createUploadRoundScope)
  const [dimensionUniform, setDimensionUniform] = useState<number[]>([])
  const [dimensionPerRound, setDimensionPerRound] = useState<UploadRoundValueMap<number[]>>({})
  const [deviceUniform, setDeviceUniform] = useState('')
  const [devicePerRound, setDevicePerRound] = useState<UploadRoundValueMap<string>>({})
  const [multiDimensionIds, setMultiDimensionIds] = useState<number[]>([])

  // N 变化 / 文件集变化 → 轮次勾选与逐轮取值全部重置为默认（第 1 轮，§5.7.2）
  useEffect(() => {
    setDimensionScopeState(createUploadRoundScope())
    setDeviceScopeState(createUploadRoundScope())
    setDimensionPerRound({})
    setDevicePerRound({})
  }, [count, resetKey])

  // 越界轮次号随 N 收缩自动丢弃（某分组 JSON 轮数少于 N 时同口径，§5.7.2）
  const dimensionScopeValue = clampUploadRoundScope(dimensionScope, count)
  const deviceScopeValue = clampUploadRoundScope(deviceScope, count)

  const dimensionIdsOf = useCallback(
    (round: number): number[] => {
      if (dimensionScopeValue.mode === 'all') return dimensionUniform
      if (dimensionScopeValue.mode === 'specific')
        return dimensionScopeValue.specificRounds.includes(round) ? dimensionUniform : []
      return dimensionPerRound[round] ?? []
    },
    [dimensionScopeValue, dimensionUniform, dimensionPerRound]
  )

  const deviceValueOf = useCallback(
    (round: number): string => {
      if (deviceScopeValue.mode === 'all') return deviceUniform
      if (deviceScopeValue.mode === 'specific')
        return deviceScopeValue.specificRounds.includes(round) ? deviceUniform : ''
      return devicePerRound[round] ?? ''
    },
    [deviceScopeValue, deviceUniform, devicePerRound]
  )

  const setDimensionScope = useCallback(
    (next: UploadRoundScopeValue) => {
      const clamped = clampUploadRoundScope(next, count)
      // 首次进入逐轮档：各轮预填当前统一值（Tab 上看到的即提交值，避免「未编辑轮次静默丢弃」）
      if (clamped.mode === 'per_round' && dimensionScopeValue.mode !== 'per_round') {
        const seeded: UploadRoundValueMap<number[]> = {}
        for (let round = 1; round <= count; round++) seeded[round] = dimensionUniform
        setDimensionPerRound(seeded)
      }
      setDimensionScopeState(clamped)
    },
    [count, dimensionScopeValue.mode, dimensionUniform]
  )

  const setDeviceScope = useCallback(
    (next: UploadRoundScopeValue) => {
      const clamped = clampUploadRoundScope(next, count)
      if (clamped.mode === 'per_round' && deviceScopeValue.mode !== 'per_round') {
        const seeded: UploadRoundValueMap<string> = {}
        for (let round = 1; round <= count; round++) seeded[round] = deviceUniform
        setDevicePerRound(seeded)
      }
      setDeviceScopeState(clamped)
    },
    [count, deviceScopeValue.mode, deviceUniform]
  )

  const dimensionIds =
    dimensionScopeValue.mode === 'per_round'
      ? (dimensionPerRound[dimensionScopeValue.activeRound] ?? [])
      : dimensionUniform

  const setDimensionIds = useCallback(
    (ids: number[]) => {
      if (dimensionScopeValue.mode === 'per_round') {
        const round = dimensionScopeValue.activeRound
        setDimensionPerRound((prev) => ({ ...prev, [round]: ids }))
      } else {
        setDimensionUniform(ids)
      }
    },
    [dimensionScopeValue.mode, dimensionScopeValue.activeRound]
  )

  const dimensionCountOf = useCallback(
    (round: number) => dimensionIdsOf(round).length,
    [dimensionIdsOf]
  )

  const deviceId =
    deviceScopeValue.mode === 'per_round'
      ? (devicePerRound[deviceScopeValue.activeRound] ?? '')
      : deviceUniform

  const setDeviceId = useCallback(
    (id: string) => {
      if (deviceScopeValue.mode === 'per_round') {
        const round = deviceScopeValue.activeRound
        setDevicePerRound((prev) => ({ ...prev, [round]: id }))
      } else {
        setDeviceUniform(id)
      }
    },
    [deviceScopeValue.mode, deviceScopeValue.activeRound]
  )

  const deviceSelectedOf = useCallback((round: number) => deviceValueOf(round) !== '', [
    deviceValueOf,
  ])

  const copyDimensionFromRound = useCallback(
    (sourceRound: number) => {
      const round = dimensionScopeValue.activeRound
      const source = dimensionIdsOf(sourceRound).slice()
      setDimensionPerRound((prev) => ({ ...prev, [round]: source }))
    },
    [dimensionScopeValue.activeRound, dimensionIdsOf]
  )

  const clearDimensionRound = useCallback(() => {
    const round = dimensionScopeValue.activeRound
    setDimensionPerRound((prev) => ({ ...prev, [round]: [] }))
  }, [dimensionScopeValue.activeRound])

  const applyDimensionRoundToAll = useCallback(() => {
    const value = dimensionIdsOf(dimensionScopeValue.activeRound).slice()
    setDimensionUniform(value)
    const seeded: UploadRoundValueMap<number[]> = {}
    for (let round = 1; round <= count; round++) seeded[round] = value
    setDimensionPerRound(seeded)
  }, [count, dimensionScopeValue.activeRound, dimensionIdsOf])

  const copyDeviceFromRound = useCallback(
    (sourceRound: number) => {
      const round = deviceScopeValue.activeRound
      const source = deviceValueOf(sourceRound)
      setDevicePerRound((prev) => ({ ...prev, [round]: source }))
    },
    [deviceScopeValue.activeRound, deviceValueOf]
  )

  const clearDeviceRound = useCallback(() => {
    const round = deviceScopeValue.activeRound
    setDevicePerRound((prev) => ({ ...prev, [round]: '' }))
  }, [deviceScopeValue.activeRound])

  const applyDeviceRoundToAll = useCallback(() => {
    const value = deviceValueOf(deviceScopeValue.activeRound)
    setDeviceUniform(value)
    const seeded: UploadRoundValueMap<string> = {}
    for (let round = 1; round <= count; round++) seeded[round] = value
    setDevicePerRound(seeded)
  }, [count, deviceScopeValue.activeRound, deviceValueOf])

  const dimensionPlan = useMemo<UploadDimensionPlan>(
    () => ({
      mode: dimensionScopeValue.mode,
      uniformIds: dimensionUniform,
      specificRounds: dimensionScopeValue.specificRounds,
      perRoundIds: dimensionPerRound,
    }),
    [dimensionScopeValue, dimensionUniform, dimensionPerRound]
  )

  const devicePlan = useMemo<UploadDevicePlan>(
    () => ({
      mode: deviceScopeValue.mode,
      uniformId: toDeviceId(deviceUniform),
      specificRounds: deviceScopeValue.specificRounds,
      perRoundIds: Object.fromEntries(
        Object.entries(devicePerRound).map(([round, value]) => [round, toDeviceId(value)])
      ) as UploadRoundValueMap<number | null>,
    }),
    [deviceScopeValue, deviceUniform, devicePerRound]
  )

  // 提交条目：取各档实际用到的全部 id 的并集（逐轮档各轮可能不同），条目必须带 name（§5.7.7）
  const selectedDimensionIds = useMemo(
    () => unionIds([dimensionUniform, ...Object.values(dimensionPerRound)]),
    [dimensionUniform, dimensionPerRound]
  )

  const toItems = useCallback(
    (ids: number[], roundScope: 'single' | 'multi'): UploadDimensionItem[] =>
      ids.map((id) => {
        const dimension = catalog.find((d) => Number(d.id) === id)
        return {
          id,
          name: dimension?.name ?? `维度 ${id}`,
          ...(typeof dimension?.weight === 'number' ? { weight: dimension.weight } : {}),
          round_scope: roundScope,
        }
      }),
    [catalog]
  )

  const dimensionItems = useMemo(
    () => toItems(selectedDimensionIds, 'single'),
    [toItems, selectedDimensionIds]
  )
  const multiDimensionItems = useMemo(
    () => toItems(multiDimensionIds, 'multi'),
    [toItems, multiDimensionIds]
  )

  const defaultDeviceId = useMemo(() => {
    if (deviceScopeValue.mode === 'per_round') return toDeviceId(devicePerRound[1] ?? '')
    return toDeviceId(deviceUniform)
  }, [deviceScopeValue.mode, devicePerRound, deviceUniform])

  return {
    roundCount: count,
    dimensionScope: dimensionScopeValue,
    setDimensionScope,
    dimensionIds,
    setDimensionIds,
    dimensionCountOf,
    deviceScope: deviceScopeValue,
    setDeviceScope,
    deviceId,
    setDeviceId,
    deviceSelectedOf,
    copyDimensionFromRound,
    clearDimensionRound,
    applyDimensionRoundToAll,
    copyDeviceFromRound,
    clearDeviceRound,
    applyDeviceRoundToAll,
    multiDimensionIds,
    setMultiDimensionIds,
    dimensionItems,
    multiDimensionItems,
    dimensionPlan,
    devicePlan,
    defaultDeviceId,
  }
}
