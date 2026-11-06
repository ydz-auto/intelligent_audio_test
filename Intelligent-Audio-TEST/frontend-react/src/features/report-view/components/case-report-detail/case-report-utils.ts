/**
 * 用例卡片共享逻辑（15_报告域.md §3.5，TestCaseReportDetail 平移）。
 * 轮次标记解析（param_code@round:N / @overall / round_number 1 基）、轮次 Tab 装配、
 * 资源 label（resourceHeaders）、结果文本格式化（timestamp/number/boolean/json/audio_file）、
 * 用例参数值格式化（布尔转「是/否」、对象 JSON）。
 */
import type {
  ReportAlgorithmResult,
  ReportReferenceParam,
  ReportResourceHeader,
} from '@/domain/models/report'

/** 轮次标记：'round:N' / 'overall' / null（无标记） */
export function parseFieldRoundTag(
  paramCode?: string,
  roundNumber?: number
): string | null {
  if (paramCode) {
    const m = paramCode.match(/@round:(\d+)$/i)
    if (m) return `round:${m[1]}`
    if (/@overall$/i.test(paramCode)) return 'overall'
  }
  const rn = roundNumber
  if (rn !== null && rn !== undefined && !Number.isNaN(Number(rn))) {
    return `round:${Number(rn)}`
  }
  return null
}

export function fieldHasRoundTag(field: { paramCode?: string; roundNumber?: number }): boolean {
  return parseFieldRoundTag(field.paramCode, field.roundNumber) !== null
}

/** 解析指标 key：提取基础名 + 轮次标记（'round:N' / 'overall' / null） */
export function parseMetricKey(k: string): { base: string; roundTag: string | null } {
  const m = k.match(/^(.*)@(round:(\d+)|overall)$/i)
  if (!m) return { base: k, roundTag: null }
  if (m[2].toLowerCase() === 'overall') return { base: m[1], roundTag: 'overall' }
  return { base: m[1], roundTag: `round:${m[3]}` }
}

/** 从 param_code 提取基础名（去掉 @round:N 后缀） */
export function getFieldBaseName(paramCode?: string, label?: string): string {
  if (paramCode) return paramCode.replace(/@round:\d+$/i, '')
  return paramCode || label || ''
}

/** 轮次标记 → 展示文案（'round:1' → 「第 1 轮」；'overall' → 「整体」，全站排版空格化） */
export function roundTagLabel(roundTag: string): string {
  if (roundTag === 'overall') return '整体'
  const n = roundTag.split(':')[1]
  return n ? `第 ${n} 轮` : roundTag
}

export interface RoundTab {
  key: string
  label: string
  roundTag: string | null
  order: number
}

interface RoundSource {
  paramCode?: string
  roundNumber?: number
}

/**
 * 轮次标记集合 → 轮次 Tab（第 1..N 轮按数字升序、「整体」恒末尾；空集合返回空数组）。
 * 标签格式「第 N 轮 / 整体」（全站排版空格化，§3.3.7）。
 */
export function roundTabsFromTags(tags: Iterable<string>): RoundTab[] {
  const tabs: RoundTab[] = []
  const seen = new Set<string>()
  for (const roundTag of tags) {
    if (!roundTag || seen.has(roundTag)) continue
    seen.add(roundTag)
    if (roundTag === 'overall') {
      tabs.push({ key: 'overall', label: '整体', roundTag, order: 9999 })
    } else {
      const n = parseInt(roundTag.split(':')[1], 10)
      tabs.push({
        key: roundTag,
        label: Number.isNaN(n) ? roundTag : `第 ${n} 轮`,
        roundTag,
        order: Number.isNaN(n) ? 50 : n,
      })
    }
  }
  return tabs.sort((a, b) => a.order - b.order)
}

/** 按轮次标记过滤字段（无标记字段恒显示；「整体」Tab 显示无标记 + overall） */
export function filterByRound<T extends RoundSource>(fields: T[], roundTag: string | null): T[] {
  if (roundTag === null || roundTag === 'overall') return fields
  return fields.filter((f) => {
    const tag = parseFieldRoundTag(f.paramCode, f.roundNumber)
    return tag === null || tag === roundTag
  })
}

/** 资源 key → 展示 label（resourceHeaders 映射；缺省清洗 `_` 前缀/任务快照名） */
export function getDeviceName(device: string | undefined, headers: ReportResourceHeader[]): string {
  const key = String(device ?? '')
  if (!key) return 'default'
  const hit = headers.find((h) => String(h.key) === key)
  if (hit) return hit.label || hit.name || key
  if (key.includes('_')) return key.split('_').slice(1).join('_')
  return key
}

/** 布尔/对象/原始值 → 展示字符串（照 V9.7.10 formatCaseParamValue） */
export function formatCaseParamValue(val: unknown): string {
  if (val === null || val === undefined || val === '') return ''
  if (typeof val === 'boolean') return val ? '是' : '否'
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val, null, 2)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

/** 时间戳/数字/布尔/JSON 类型格式化（照 V9.7.10 getResultTextValue） */
export function formatResultValue(value: unknown, paramType?: string): string {
  if (value === null || value === undefined) return '无数据'
  // 时间戳类型：纯数字（秒/毫秒）与 ISO 均格式化为 YYYY-MM-DD HH:mm:ss
  if (paramType === 'timestamp') {
    const ts = typeof value === 'string' ? value : String(value)
    if (/^\d{10,13}$/.test(ts.trim())) {
      const ms = ts.trim().length === 10 ? Number(ts.trim()) * 1000 : Number(ts.trim())
      const d = new Date(ms)
      if (!Number.isNaN(d.getTime())) return formatDateTime(d)
    }
    const d = new Date(ts)
    if (!Number.isNaN(d.getTime())) return formatDateTime(d)
    return ts
  }
  if (paramType === 'number') {
    if (typeof value === 'number') {
      return Number.isInteger(value) ? String(value) : value.toFixed(2)
    }
    const num = Number(value)
    if (!Number.isNaN(num)) return Number.isInteger(num) ? String(num) : num.toFixed(2)
    return String(value)
  }
  if (paramType === 'boolean') {
    if (typeof value === 'boolean') return value ? '是' : '否'
    return String(value)
  }
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      if (typeof parsed === 'object' && parsed !== null) {
        return JSON.stringify(parsed, null, 2)
      }
    } catch {
      /* 非 JSON 原样返回 */
    }
    return value
  }
  if (typeof value === 'object' && value !== null) {
    const rec = value as { text?: unknown; value?: unknown }
    if (rec.text !== undefined) return String(rec.text)
    if (rec.value !== undefined) return String(rec.value)
    return JSON.stringify(value, null, 2)
  }
  return String(value)
}

function formatDateTime(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** 判断字符串是否为可解析 JSON 对象（照 V9.7.10 isJsonString） */
export function isJsonString(text: unknown): boolean {
  if (typeof text !== 'string') return false
  const t = text.trim()
  if (!t) return false
  if (!/^[\[{]/.test(t)) return false
  try {
    const parsed = JSON.parse(t)
    return typeof parsed === 'object' && parsed !== null
  } catch {
    return false
  }
}

/** JSON 字符串 → 格式化输出（失败原样返回） */
export function formatJson(text: unknown): string {
  const t = typeof text === 'string' ? text : String(text ?? '')
  try {
    return JSON.stringify(JSON.parse(t), null, 2)
  } catch {
    return t
  }
}

/** 多轮聚合字段（后端 aggregated 原样；前端兜底自算同形） */
export interface MultiRoundAggregated {
  avg_wer?: number
  avg_llm_judge?: number
  avg_latency?: number
  interruption_count?: number
  [key: string]: number | undefined
}

/** 真实多轮数据源（rounds 数组 + 可选后端聚合） */
export interface MultiRoundSource {
  rounds: Record<string, unknown>[]
  aggregated?: MultiRoundAggregated
}

/**
 * 多轮对话结果的 rounds 源判定（照 V9.7.10 `reportService.ts parseMultiRoundResult` +
 * `TestCaseReportDetail.vue:412-418`，INT-2120）。**只有真正的 rounds 源**才判多轮：
 *
 * ① 项自身 `rounds` 为数组（V9.7.10 主口径 / mock 形态）；
 * ② `value` 为对象且内含 `rounds` 数组（快照嵌套形态，V9.7.10 第二口径）。
 *
 * 关键反例（report 420 / 用例 DD001 真实库实测）：`round_details@round:N`、
 * `llm_round_evaluations@round:N` 这类按轮展开的 json 项 `value` 也是数组，但不是
 * rounds 源；即便 `param_code=rounds` 的扁平项 `value` 就是轮次数组，V9.7.10 也只认
 * 「项自身 / value 对象上的 rounds 字段」，不认数组 value → 该用例**整块不渲染**
 * （INT-2120 验收首条）。不合成、不从数组 value 反推 rounds。
 */
export function findMultiRoundSource(
  algorithmResults: ReportAlgorithmResult[] | undefined
): MultiRoundSource | null {
  for (const item of algorithmResults ?? []) {
    const direct = (item as { rounds?: unknown }).rounds
    if (Array.isArray(direct)) {
      if (direct.length > 0) {
        return {
          rounds: direct as Record<string, unknown>[],
          aggregated: (item as { aggregated?: MultiRoundAggregated }).aggregated,
        }
      }
      continue
    }
    const value = item.value
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const nested = (value as { rounds?: unknown }).rounds
      if (Array.isArray(nested) && nested.length > 0) {
        return {
          rounds: nested as Record<string, unknown>[],
          aggregated: (value as { aggregated?: MultiRoundAggregated }).aggregated,
        }
      }
    }
  }
  return null
}

/** 归一化 algorithmResults（camel/snake 双字段兼容） */
export function normalizeAlgorithmResult(
  item: ReportAlgorithmResult
): ReportAlgorithmResult & { param_code: string; param_type?: string; round_number?: number; dimension_name?: string } {
  return {
    ...item,
    param_code: item.paramCode,
    param_type: item.paramType,
    round_number: item.roundNumber,
    dimension_name: item.dimensionName,
  }
}

/**
 * 结果文本字段读取（照 V9.7.10 getResultTextValue）：
 * 对比模式先精确匹配 device+param_code，再回退大小写/包含匹配；单设备模式按 param_code 首条。
 */
export function getResultTextValue(
  device: string | undefined,
  paramCode: string,
  algorithmResults: ReportAlgorithmResult[],
  isComparison: boolean
): string {
  const normed = (algorithmResults ?? []).map(normalizeAlgorithmResult)
  let item
  if (isComparison && device !== undefined && device !== 'default') {
    const deviceLower = String(device).toLowerCase()
    item =
      normed.find((i) => i.device === device && i.param_code === paramCode) ??
      normed.find(
        (i) =>
          i.device &&
          (i.device.toLowerCase().includes(deviceLower) || deviceLower.includes(i.device.toLowerCase())) &&
          i.param_code === paramCode
      )
  } else {
    item = normed.find((i) => i.param_code === paramCode)
  }
  if (!item || item.value === undefined || item.value === null) return '无数据'
  return formatResultValue(item.value, item.param_type)
}

/** 从 referenceParams 提取参考文本（字符串 / {text|value}） */
export function getReferenceTextValue(code: string, referenceParams: Record<string, ReportReferenceParam>): string {
  const data = referenceParams[code]
  if (!data) return ''
  if (typeof data === 'string') return data
  return (data.text ?? data.value ?? '') as string
}

/** LLM 评语提取（evaluation.reasoning → raw_response 解析 reasoning/analysis） */
export function extractLlmReasoning(evaluation: Record<string, unknown> | undefined): string {
  if (!evaluation) return ''
  if (typeof evaluation.reasoning === 'string' && evaluation.reasoning) return evaluation.reasoning
  const raw = evaluation.raw_response
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      return (parsed?.reasoning || parsed?.analysis || '') as string
    } catch {
      return ''
    }
  }
  return ''
}
