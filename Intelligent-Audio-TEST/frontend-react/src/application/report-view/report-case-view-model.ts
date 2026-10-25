/**
 * 具体用例三视图纯函数（application 层，15_报告域.md §3.3.7 三视图 / §3.5.10，INT-1738）。
 *
 * 数据事实（§1.3 真实库实测）：`report_cases` **一行 = 一个用例 × 一个资源**，
 * 该行 `results` 恰好 1 条、`metrics` 只含该资源的键；`searchCases` 的 `total` 是结果行数。
 * 所以：
 * - 用例视图必须按 `test_case_id` 合并，`results / metrics / algorithmResults / audios / logs`
 *   按资源**取并集**（同 resource 后到覆盖），组 / 节点计数与叶表行一律由并集算；
 * - 设备视图 / 结果类型视图的第 1 层节点由并集后的资源 / 结果类型聚合；
 * - 结果类型现网只能从 `resource_headers[].result_type`（非空即用）或资源键后缀解析，缺省「默认」
 *   （§10-10）；全部为默认时不渲染「结果类型视图」档。
 *
 * 本文件是纯函数集合（可单测，无 React / 无请求）。
 */
import { extractCaseResourceMetrics } from './case-matrix'
import { parseMetricKey } from '@/features/report-view/components/case-report-detail/case-report-utils'
import type {
  ReportAlgorithmResult,
  ReportAudioItem,
  ReportCaseItem,
  ReportCaseMetrics,
  ReportCaseResult,
  ReportMetricDataGroup,
  ReportResourceHeader,
} from '@/domain/models/report'

/** 三视图标识（设备视图 = resource，结果类型视图 = resultType） */
export type ReportCaseView = 'case' | 'resource' | 'resultType'

/** 结果类型白名单（仅用于中文映射；未知值原样 mono 显示，§10-10） */
export const RESULT_TYPE_CODES = ['realtime', 'final', 'recording', 'default'] as const
export const DEFAULT_RESULT_TYPE = 'default'

const RESULT_TYPE_LABELS: Record<string, string> = {
  realtime: '实时',
  final: '最终',
  recording: '录音',
  default: '默认',
}

/** 结果类型 → 中文（实时 / 最终 / 录音 / 默认；未知值原样） */
export function resultTypeText(code?: string | null): string {
  const key = String(code ?? '').trim().toLowerCase()
  if (!key) return RESULT_TYPE_LABELS[DEFAULT_RESULT_TYPE]
  return RESULT_TYPE_LABELS[key] ?? key
}

/**
 * 资源 → 结果类型（§10-10 解析顺序）：
 * ① `resource_headers[].result_type` 非空即用 → ② 资源键最后一个 `-` 段命中白名单 → ③「默认」。
 * 真实库现状：206 份报告无一例命中 ①②，全部解析为「默认」。
 */
export function parseResultType(
  resourceKey?: string | null,
  headers: ReportResourceHeader[] = []
): string {
  const key = String(resourceKey ?? '')
  const declared = headers.find((h) => String(h.key) === key)?.result_type
  if (declared && String(declared).trim()) return String(declared).trim().toLowerCase()
  const tail = key.split('-').filter(Boolean).pop()?.toLowerCase()
  if (tail && (RESULT_TYPE_CODES as readonly string[]).includes(tail)) return tail
  return DEFAULT_RESULT_TYPE
}

/** 至少一个非「默认」结果类型（决定是否渲染「结果类型视图」档，§3.3.7） */
export function hasNonDefaultResultType(
  resourceKeys: string[],
  headers: ReportResourceHeader[] = []
): boolean {
  return resourceKeys.some((k) => parseResultType(k, headers) !== DEFAULT_RESULT_TYPE)
}

/** 合并后的用例行（并集结果额外带上按资源分组的日志，不落后端字段） */
export interface MergedReportCase extends ReportCaseItem {
  /** 按资源保留的详细日志（各资源不同时按资源分节；相同时为 undefined） */
  resourceLogs?: Record<string, string>
}

/** 用例行涉及的全部资源键（results ∪ metrics） */
export function caseResourceKeys(item: ReportCaseItem): string[] {
  const keys = new Set<string>()
  for (const r of item.results ?? []) if (r.resource) keys.add(String(r.resource))
  const metrics = item.metrics
  if (Array.isArray(metrics)) {
    for (const g of metrics) if (g?.resource) keys.add(String(g.resource))
  } else if (metrics) {
    for (const k of Object.keys(metrics)) keys.add(k)
  }
  return [...keys]
}

/** metrics 双格式按资源合并（同 resource 后到覆盖；不统一转格式，§1.3 双格式契约） */
function mergeMetrics(rows: ReportCaseItem[]): ReportCaseMetrics {
  const arrayFormat = rows.some((r) => Array.isArray(r.metrics))
  if (arrayFormat) {
    const map = new Map<string, ReportMetricDataGroup>()
    for (const row of rows) {
      if (!Array.isArray(row.metrics)) continue
      for (const group of row.metrics) {
        if (!group?.resource) continue
        map.set(String(group.resource), group)
      }
    }
    return [...map.values()]
  }
  const merged: Record<string, Record<string, number>> = {}
  for (const row of rows) {
    if (Array.isArray(row.metrics) || !row.metrics) continue
    for (const [resource, metrics] of Object.entries(row.metrics)) {
      merged[resource] = { ...(merged[resource] ?? {}), ...metrics }
    }
  }
  return merged
}

/** 合并同一用例的多资源行（单行原样返回，避免无谓拷贝） */
export function mergeCaseRows(rows: ReportCaseItem[]): MergedReportCase {
  if (rows.length === 1) return rows[0]
  const first = rows[0]
  const RESULTS_EMPTY: ReportCaseResult[] = []

  const resultMap = new Map<string, ReportCaseResult>()
  const audioList: ReportAudioItem[] = []
  const audioSeen = new Set<string>()
  const algoList: ReportAlgorithmResult[] = []
  const algoSeen = new Set<string>()
  const resourceLogs: Record<string, string> = {}

  for (const row of rows) {
    for (const r of row.results ?? []) resultMap.set(String(r.resource), r)
    for (const a of row.audios ?? []) {
      const key = String(a.audio_id)
      if (audioSeen.has(key)) continue
      audioSeen.add(key)
      audioList.push(a)
    }
    for (const ar of row.algorithmResults ?? []) {
      const key = `${ar.paramCode}::${ar.device ?? ''}`
      if (algoSeen.has(key)) continue
      algoSeen.add(key)
      algoList.push(ar)
    }
    // 日志按资源保留（一行 = 一个资源）
    if (row.logs) {
      const resource = caseResourceKeys(row)[0] ?? DEFAULT_RESULT_TYPE
      if (!resourceLogs[resource]) resourceLogs[resource] = row.logs
    }
  }

  const results = [...resultMap.values()].sort((a, b) =>
    String(a.resource).localeCompare(String(b.resource), 'zh-CN')
  )
  const distinctLogs = new Set(Object.values(resourceLogs))
  const firstLog = first.logs ?? Object.values(resourceLogs)[0]

  return {
    ...first,
    results: results.length > 0 ? results : RESULTS_EMPTY,
    metrics: mergeMetrics(rows),
    audios: audioList,
    algorithmResults: algoList,
    logs: firstLog,
    resourceLogs: distinctLogs.size > 1 ? resourceLogs : undefined,
  }
}

/** 按 test_case_id 合并整批结果行（保持服务端返回顺序） */
export function mergeCaseRowsByCaseId(rows: ReportCaseItem[]): MergedReportCase[] {
  const buckets = new Map<string, ReportCaseItem[]>()
  const order: string[] = []
  for (const row of rows) {
    const id = String(row.id ?? '')
    if (!buckets.has(id)) {
      buckets.set(id, [])
      order.push(id)
    }
    buckets.get(id)!.push(row)
  }
  return order.map((id) => mergeCaseRows(buckets.get(id)!))
}

/** 设备视图第 1 层节点（设备/API） */
export interface ResourceNode {
  /** 唯一键 = `resource_headers[].key`（对比报告同一设备不同任务前缀是两个节点，不合并） */
  key: string
  /** 展示名（`getDeviceName` 口径：label → name → key；解析不出用「未知设备 / 未知 API」） */
  name: string
  /** device / api（图标 Smartphone / ArrowLeftRight） */
  kind: 'device' | 'api'
  version?: string
  /** 对比报告资源键 `t{taskId}-…` 前缀徽章（同设备不同任务区分） */
  taskPrefix?: string
  cases: MergedReportCase[]
  count: number
}

/** 结果类型视图第 1 层节点 */
export interface ResultTypeNode {
  key: string
  label: string
  cases: MergedReportCase[]
  count: number
}

/** 资源展示名（与 case-report-utils getDeviceName 同口径，纯函数本地实现避免循环依赖） */
function resourceDisplayName(key: string, headers: ReportResourceHeader[]): string {
  const header = headers.find((h) => String(h.key) === key)
  if (header) return header.label || header.name || key
  if (key.includes('_')) return key.split('_').slice(1).join('_')
  return key
}

/** 资源 → 结果类型（results 自带 result_type 优先，其次键解析） */
function resultTypeOfResult(result: ReportCaseResult, headers: ReportResourceHeader[]): string {
  const declared = result.result_type
  if (declared && String(declared).trim()) return String(declared).trim().toLowerCase()
  return parseResultType(result.resource, headers)
}

/** 按资源聚合用例（设备视图第 1 层，§3.3.7）：顺序照 resource_headers，未知资源追加末尾 */
export function groupCasesByResource(
  cases: MergedReportCase[],
  headers: ReportResourceHeader[] = []
): ResourceNode[] {
  const buckets = new Map<string, MergedReportCase[]>()
  for (const c of cases) {
    for (const key of caseResourceKeys(c)) {
      if (!buckets.has(key)) buckets.set(key, [])
      buckets.get(key)!.push(c)
    }
  }
  const ordered: string[] = []
  for (const h of headers) {
    const key = String(h.key)
    if (buckets.has(key) && !ordered.includes(key)) ordered.push(key)
  }
  for (const key of buckets.keys()) if (!ordered.includes(key)) ordered.push(key)

  return ordered.map((key) => {
    const header = headers.find((h) => String(h.key) === key)
    const isApi = header?.type === 'api' || (!header && /^api/i.test(key))
    const taskPrefix = key.match(/^t(\d+)-/)?.[0].slice(1, -1)
    return {
      key,
      name: resourceDisplayName(key, headers) || (isApi ? '未知 API' : '未知设备'),
      kind: isApi ? 'api' : 'device',
      version: header?.version,
      taskPrefix,
      cases: buckets.get(key) ?? [],
      count: (buckets.get(key) ?? []).length,
    }
  })
}

/** 按结果类型聚合用例（结果类型视图第 1 层）：白名单顺序在前，「默认」恒末尾 */
export function groupCasesByResultType(
  cases: MergedReportCase[],
  headers: ReportResourceHeader[] = []
): ResultTypeNode[] {
  const buckets = new Map<string, MergedReportCase[]>()
  for (const c of cases) {
    const types = new Set<string>()
    for (const r of c.results ?? []) types.add(resultTypeOfResult(r, headers))
    if (types.size === 0) for (const key of caseResourceKeys(c)) types.add(parseResultType(key, headers))
    for (const t of types) {
      if (!buckets.has(t)) buckets.set(t, [])
      buckets.get(t)!.push(c)
    }
  }
  const rank = (code: string) => {
    const idx = (RESULT_TYPE_CODES as readonly string[]).indexOf(code as never)
    if (code === DEFAULT_RESULT_TYPE) return 99
    return idx >= 0 ? idx : 50
  }
  return [...buckets.entries()]
    .sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0], 'zh-CN'))
    .map(([key, list]) => ({
      key,
      label: resultTypeText(key),
      cases: list,
      count: list.length,
    }))
}

/** 叶表「结果对比」一行（§3.3.7 叶表：行集按视图不同） */
export interface ResultComparisonRow {
  key: string
  /** 设备/API 资源键（设备视图下为空，改用结果类型列） */
  resource?: string
  /** 结果类型（结果类型视图下为空，改用资源列） */
  resultType?: string
  status?: string
  startTime?: string
  metrics: Record<string, number>
}

export interface ResultComparisonOptions {
  view: ReportCaseView
  /** 设备视图：当前节点资源键 */
  resourceKey?: string
  /** 结果类型视图：当前节点结果类型 */
  resultType?: string
  /** 显示设置已选资源（`undefined` = 不过滤；`[]` = 全部取消） */
  selectedResources?: string[]
  /** 显示设置已选结果类型（`undefined` = 不过滤；`[]` = 全部取消） */
  selectedResultTypes?: string[]
  headers?: ReportResourceHeader[]
}

/**
 * 叶表行集：
 * - 用例视图 = 设备/API × result_type；
 * - 设备视图 = 当前资源的 result_type；
 * - 结果类型视图 = 当前 result_type 下的设备/API。
 * 行一律由**并集后的 results** 展开；无 results → 空数组（表区空态）。
 */
export function buildResultComparisonRows(
  item: ReportCaseItem,
  opts: ResultComparisonOptions
): ResultComparisonRow[] {
  const headers = opts.headers ?? []
  const resourceMetrics = extractCaseResourceMetrics(item)
  const results = item.results ?? []
  const selectedResources = opts.selectedResources
  const selectedResultTypes = opts.selectedResultTypes
  const keepResource = (key: string) =>
    selectedResources === undefined || selectedResources.includes(key)
  const keepType = (type: string) =>
    selectedResultTypes === undefined || selectedResultTypes.includes(type)

  if (opts.view === 'resource') {
    const key = opts.resourceKey ?? ''
    const rows = results
      .filter((r) => String(r.resource) === key)
      .map((r) => ({ r, type: resultTypeOfResult(r, headers) }))
    const types = new Map<string, ResultComparisonRow>()
    for (const { r, type } of rows) {
      if (!keepType(type)) continue
      if (types.has(type)) continue
      types.set(type, {
        key: `${key}::${type}`,
        resultType: type,
        status: r.status,
        startTime: r.startTime,
        metrics: resourceMetrics[key] ?? {},
      })
    }
    return [...types.values()]
  }

  if (opts.view === 'resultType') {
    const type = opts.resultType ?? DEFAULT_RESULT_TYPE
    const rows = results.filter((r) => resultTypeOfResult(r, headers) === type)
    const seen = new Map<string, ResultComparisonRow>()
    for (const r of rows) {
      const key = String(r.resource)
      if (!keepResource(key) || seen.has(key)) continue
      seen.set(key, {
        key: `${key}::${type}`,
        resource: key,
        status: r.status,
        startTime: r.startTime,
        metrics: resourceMetrics[key] ?? {},
      })
    }
    return [...seen.values()]
  }

  // 用例视图：设备/API × result_type
  const out: ResultComparisonRow[] = []
  const seen = new Set<string>()
  for (const r of results) {
    const key = String(r.resource)
    const type = resultTypeOfResult(r, headers)
    if (!keepResource(key) || !keepType(type)) continue
    const rowKey = `${key}::${type}`
    if (seen.has(rowKey)) continue
    seen.add(rowKey)
    out.push({
      key: rowKey,
      resource: key,
      resultType: type,
      status: r.status,
      startTime: r.startTime,
      metrics: resourceMetrics[key] ?? {},
    })
  }
  return out
}

/** 用例涉及的全部指标 key（资源级去重，未去轮次后缀） */
export function collectMetricKeys(cases: ReportCaseItem[]): string[] {
  const keys = new Set<string>()
  for (const item of cases) {
    const resourceMetrics = extractCaseResourceMetrics(item)
    for (const metrics of Object.values(resourceMetrics)) {
      for (const key of Object.keys(metrics)) keys.add(key)
    }
  }
  return [...keys]
}

/** 指标 key → 去轮次后缀的基础维度集合（评估维度选择器只列基础维度，§3.5.10） */
export function collectBaseDimensions(metricKeys: string[]): string[] {
  const bases = new Set<string>()
  for (const key of metricKeys) bases.add(parseMetricKey(key).base)
  return [...bases]
}

/** 当前数据里出现的轮次标记（`overall` / `round:N`，按轮次升序、「整体」末尾） */
export function collectRounds(metricKeys: string[]): string[] {
  const tags = new Set<string>()
  for (const key of metricKeys) {
    const tag = parseMetricKey(key).roundTag
    if (tag) tags.add(tag)
  }
  return [...tags].sort((a, b) => {
    if (a === b) return 0
    if (a === 'overall') return 1
    if (b === 'overall') return -1
    return Number(a.split(':')[1]) - Number(b.split(':')[1])
  })
}

/** 叶表指标列（一个已选主维度一列，§3.3.7 / §3.5.10，INT-1774） */
export interface LeafMetricColumn {
  /** 列 key（= 基础维度名，稳定；轮次已不是列维度） */
  key: string
  /** 列头文案（**只用基础维度名，不带轮次后缀**） */
  label: string
  /** 该列在数据里的取值键 = `{基础维度}{当前激活 Tab 的轮次后缀}`（无轮次后缀即基础维度本身） */
  metricKey: string
  /** 基础维度名 */
  base: string
  /** 当前激活轮次标记（'' = 无轮次后缀） */
  round: string
}

/**
 * 叶表列集 = **已选主维度，一维一列**（INT-1774：轮次移出列，改为标题行 Tab）。
 * 列头只用基础维度名；取值键按 `activeRoundTag` 拼轮次后缀，缺该轮数据时由表格显示「—」
 * （**不回退基础维度键**——多轮用例的指标键带后缀，回退会让整列变「—」之外还会取错值）。
 * 子维度默认不进叶表，由 `includeSubDimensions` 控制（§3.5.10）。
 *
 * @param metricKeys 本用例全部指标键（未去轮次后缀）
 * @param selectedBaseDimensions 显示设置「评估维度」已选（去后缀的基础维度名）
 * @param activeRoundTag 当前激活轮次的标记（`null` = 无轮次后缀）
 */
export function buildLeafMetricColumns(
  metricKeys: string[],
  selectedBaseDimensions: string[],
  activeRoundTag: string | null,
  includeSubDimensions: boolean,
  subDimensionNames: string[] = []
): LeafMetricColumn[] {
  const availableBases = new Set(metricKeys.map((key) => parseMetricKey(key).base))
  const subs = new Set(subDimensionNames)
  const round = activeRoundTag ?? ''
  const columns: LeafMetricColumn[] = []
  for (const base of selectedBaseDimensions) {
    if (!availableBases.has(base)) continue
    if (subs.has(base) && !includeSubDimensions) continue
    columns.push({
      key: base,
      label: base,
      metricKey: round ? `${base}@${round}` : base,
      base,
      round,
    })
  }
  return columns
}

/** 数值精度（all_metrics[].decimal_places，默认 2） */
export function metricDecimalPlaces(
  metricKey: string,
  configs: { name: string; decimal_places?: number }[]
): number {
  const base = parseMetricKey(metricKey).base
  return (
    configs.find((m) => m.name === base)?.decimal_places ??
    configs.find((m) => m.name === metricKey)?.decimal_places ??
    2
  )
}

/** 叶表数值格式化（缺值 / null / 非数字「—」；真实库 metrics 存在 null 值） */
export function formatMetricCell(
  value: number | undefined | null,
  decimalPlaces: number
): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value.toFixed(decimalPlaces)
}
