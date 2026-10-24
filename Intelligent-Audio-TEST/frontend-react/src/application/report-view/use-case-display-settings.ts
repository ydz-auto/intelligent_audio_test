/**
 * 用例卡「维度显示可选」状态（application 层，15_报告域.md §3.5.10，INT-1738）。
 *
 * 口径：
 * - **默认全选**（= 现状，不破坏首次进入的呈现）；唯一例外是叶表列集默认「主维度 × 默认轮次」
 *   （由叶表按 `defaultLeafRounds` 自行决定，不落本状态）。
 * - **区级一份状态**（作用于该报告内全部用例卡 + 三视图叶表），不进 URL；
 *   `localStorage` 键 `iatp:report:case-display:v1`，按 `report.id` 命名空间，切报告回全选。
 * - **导出强制全显**（`isExporting`）：忽略本设置，且不渲染「显示设置」按钮。
 * - 状态存「隐藏项」而非「已选项」：新增维度 / 轮次自动全选。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

/** 卡片内容块（一级开关；执行结果带 5 个子项） */
export const CONTENT_BLOCK_KEYS = [
  'resultComparison',
  'metricTable',
  'multiRound',
  'execution',
  'description',
  'logs',
] as const
export type ContentBlockKey = (typeof CONTENT_BLOCK_KEYS)[number]

/** 执行结果子项（与父开关联动） */
export const EXECUTION_CHILD_KEYS = [
  'reference',
  'caseParams',
  'evaluation',
  'deviceResults',
  'timeline',
  'audio',
] as const
export type ExecutionChildKey = (typeof EXECUTION_CHILD_KEYS)[number]

export const CONTENT_BLOCK_LABELS: Record<ContentBlockKey, string> = {
  resultComparison: '结果对比',
  metricTable: '评分指标',
  multiRound: '多轮对话结果',
  execution: '执行结果',
  description: '用例描述',
  logs: '详细日志',
}

export const EXECUTION_CHILD_LABELS: Record<ExecutionChildKey, string> = {
  reference: '参考数据',
  caseParams: '用例参数',
  evaluation: '评估结果',
  deviceResults: '设备·API 执行结果',
  timeline: '时间轴对比',
  audio: '音频',
}

export interface CaseDisplaySettings {
  /** 隐藏的内容块 */
  hiddenBlocks: ContentBlockKey[]
  /** 隐藏的执行结果子项 */
  hiddenExecution: ExecutionChildKey[]
  /** 隐藏的评估维度（去轮次后缀的基础维度名） */
  hiddenMetrics: string[]
  /** 隐藏的轮次（`overall` / `round:N`） */
  hiddenRounds: string[]
  /** 隐藏的资源键 */
  hiddenResources: string[]
  /** 隐藏的结果类型 */
  hiddenResultTypes: string[]
  /** 叶表包含子维度（默认关，§3.5.10） */
  includeSubDimensions: boolean
}

export const DEFAULT_CASE_DISPLAY_SETTINGS: CaseDisplaySettings = {
  hiddenBlocks: [],
  hiddenExecution: [],
  hiddenMetrics: [],
  hiddenRounds: [],
  hiddenResources: [],
  hiddenResultTypes: [],
  includeSubDimensions: false,
}

export const CASE_DISPLAY_STORAGE_KEY = 'iatp:report:case-display:v1'

function normalize(raw: unknown): CaseDisplaySettings {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_CASE_DISPLAY_SETTINGS }
  const rec = raw as Partial<CaseDisplaySettings>
  const list = <T extends string>(v: unknown, allowed: readonly T[]): T[] =>
    Array.isArray(v) ? v.filter((x): x is T => allowed.includes(x as T)) : []
  return {
    hiddenBlocks: list(rec.hiddenBlocks, CONTENT_BLOCK_KEYS),
    hiddenExecution: list(rec.hiddenExecution, EXECUTION_CHILD_KEYS),
    hiddenMetrics: Array.isArray(rec.hiddenMetrics) ? rec.hiddenMetrics.filter((x) => typeof x === 'string') : [],
    hiddenRounds: Array.isArray(rec.hiddenRounds) ? rec.hiddenRounds.filter((x) => typeof x === 'string') : [],
    hiddenResources: Array.isArray(rec.hiddenResources) ? rec.hiddenResources.filter((x) => typeof x === 'string') : [],
    hiddenResultTypes: Array.isArray(rec.hiddenResultTypes)
      ? rec.hiddenResultTypes.filter((x) => typeof x === 'string')
      : [],
    includeSubDimensions: rec.includeSubDimensions === true,
  }
}

function readStore(reportId: number): CaseDisplaySettings {
  if (typeof window === 'undefined') return { ...DEFAULT_CASE_DISPLAY_SETTINGS }
  try {
    const raw = window.localStorage.getItem(CASE_DISPLAY_STORAGE_KEY)
    if (!raw) return { ...DEFAULT_CASE_DISPLAY_SETTINGS }
    const parsed = JSON.parse(raw) as Record<string, unknown>
    return normalize(parsed[String(reportId)])
  } catch {
    return { ...DEFAULT_CASE_DISPLAY_SETTINGS }
  }
}

function writeStore(reportId: number, settings: CaseDisplaySettings) {
  if (typeof window === 'undefined') return
  try {
    const raw = window.localStorage.getItem(CASE_DISPLAY_STORAGE_KEY)
    const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {}
    parsed[String(reportId)] = settings
    window.localStorage.setItem(CASE_DISPLAY_STORAGE_KEY, JSON.stringify(parsed))
  } catch {
    /* localStorage 不可用（隐私模式 / 配额）时静默降级为会话内状态 */
  }
}

/** 折叠有默认值的总项数（「已隐藏 {n} 项」） */
export function countHiddenOptions(settings: CaseDisplaySettings): number {
  return (
    settings.hiddenBlocks.length +
    settings.hiddenExecution.length +
    settings.hiddenMetrics.length +
    settings.hiddenRounds.length +
    settings.hiddenResources.length +
    settings.hiddenResultTypes.length
  )
}

/** 内容块是否显示（执行结果父块 = 父开关 + 任一子项） */
export function isBlockVisible(settings: CaseDisplaySettings, key: ContentBlockKey): boolean {
  if (settings.hiddenBlocks.includes(key)) return false
  if (key === 'execution') {
    return EXECUTION_CHILD_KEYS.some((child) => !settings.hiddenExecution.includes(child))
  }
  return true
}

/** 执行结果子项是否显示 */
export function isExecutionChildVisible(
  settings: CaseDisplaySettings,
  key: ExecutionChildKey
): boolean {
  if (settings.hiddenBlocks.includes('execution')) return false
  return !settings.hiddenExecution.includes(key)
}

export interface UseCaseDisplaySettingsResult {
  /** 生效设置（导出态强制全显） */
  settings: CaseDisplaySettings
  /** 用户设置（导出态也保留，便于恢复） */
  stored: CaseDisplaySettings
  /** 隐藏项计数（Badge「已隐藏 {n} 项」） */
  hiddenCount: number
  /** 是否全选 */
  isAllSelected: boolean
  update: (patch: Partial<CaseDisplaySettings>) => void
  reset: () => void
}

/**
 * 显示设置状态（会话内存 + 本地偏好，按 report.id 隔离）。
 * `isExporting` 时返回全选且不回写本地偏好（导出 = 落库快照全文）。
 */
export function useCaseDisplaySettings(
  reportId: number,
  isExporting = false
): UseCaseDisplaySettingsResult {
  const [stored, setStored] = useState<CaseDisplaySettings>(() => readStore(reportId))

  useEffect(() => {
    setStored(readStore(reportId))
  }, [reportId])

  const update = useCallback(
    (patch: Partial<CaseDisplaySettings>) => {
      setStored((prev) => {
        const next = { ...prev, ...patch }
        writeStore(reportId, next)
        return next
      })
    },
    [reportId]
  )

  const reset = useCallback(() => {
    const next = { ...DEFAULT_CASE_DISPLAY_SETTINGS }
    writeStore(reportId, next)
    setStored(next)
  }, [reportId])

  const settings = useMemo(
    () => (isExporting ? { ...DEFAULT_CASE_DISPLAY_SETTINGS } : stored),
    [isExporting, stored]
  )

  const hiddenCount = countHiddenOptions(stored)
  return {
    settings,
    stored,
    hiddenCount,
    isAllSelected: hiddenCount === 0,
    update,
    reset,
  }
}
