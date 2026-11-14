/**
 * Auto 进度展示归约（application 层；INT-2474 §9.4）。
 *
 * 把 `auto_step` / `run_paused` 的原始水位（usage / limits / ratios）整理成
 * 界面直接可渲染的行与文案，供进度面板、运行时间线与终态提示共用一份口径：
 * - 五个预算维度用同一套键（AGENT_BUDGET_DIMENSION）与中文名；
 * - `limit` 缺省 / ≤0 的维度视为未启用，不渲染、不参与最高比例；
 * - 终态（成功 / 超预算 / 熔断 / 失败 / 取消）由 run 状态 + 后端错误码判定，
 *   **不把超预算或熔断展示成成功**。
 *
 * 纯函数、无副作用：界面层与单测共用。
 */
import {
  AGENT_AUTO_COPY,
  AGENT_AUTO_ERROR_CODE,
  AGENT_BUDGET_DIMENSION,
  AGENT_BUDGET_DIMENSION_LABELS,
  AGENT_RUN_MODE,
  AGENT_RUN_PAUSE_REASON,
  AGENT_RUN_STATUS,
  type AgentAutoProgress,
  type AgentAutoUsage,
  type AgentBudgetDimension,
  type AgentRun,
  type AgentRunBudget,
  type AgentRunPauseReason,
} from '@/domain/models/agent'

/** 单个预算维度的展示行 */
export interface AutoBudgetRow {
  dimension: AgentBudgetDimension
  label: string
  /** 实际用量（已换算成展示单位：分钟 / MB） */
  used: number
  /** 上限（已换算；undefined=该维度未启用） */
  limit?: number
  /** 消耗比（0–1；limit 缺省时为 undefined） */
  ratio?: number
  /** 「已用 / 上限 单位」；未启用时只显示已用 */
  text: string
}

const BYTES_PER_MB = 1024 * 1024
const SECONDS_PER_MINUTE = 60

/** 秒 → 分钟（保留一位小数，整数不带小数） */
export function toMinutes(seconds: number): number {
  const minutes = seconds / SECONDS_PER_MINUTE
  return Math.round(minutes * 10) / 10
}

/** 字节 → MB（保留一位小数） */
export function toMegabytes(bytes: number): number {
  return Math.round((bytes / BYTES_PER_MB) * 10) / 10
}

/** 比例 → 百分比整数（0.82 → 82%）；非法值返回 0 */
export function formatPercent(ratio: number | undefined): string {
  if (ratio === undefined || !Number.isFinite(ratio)) return '0%'
  return `${Math.round(ratio * 100)}%`
}

/** 毫秒无关的时长文案（进度面板「已用时长」） */
export function formatElapsed(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0 秒'
  if (seconds < 60) return `${Math.round(seconds)} 秒`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return rest > 0 ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`
}

/** 每维度的用量换算（展示单位与原始单位同一口径，避免上游两处各算一遍） */
function dimensionValues(
  usage: AgentAutoUsage,
  limits: AgentRunBudget | undefined
): Record<
  AgentBudgetDimension,
  { used: number; limit?: number; unit: string }
> {
  return {
    [AGENT_BUDGET_DIMENSION.ROUNDS]: {
      used: usage.rounds,
      limit: limits?.maxRounds,
      unit: AGENT_AUTO_COPY.unitRounds,
    },
    [AGENT_BUDGET_DIMENSION.TOOL_CALLS]: {
      used: usage.toolCalls,
      limit: limits?.maxToolCalls,
      unit: AGENT_AUTO_COPY.unitToolCalls,
    },
    [AGENT_BUDGET_DIMENSION.TOKENS]: {
      used: usage.tokens,
      limit: limits?.maxTokens,
      unit: AGENT_AUTO_COPY.unitTokens,
    },
    [AGENT_BUDGET_DIMENSION.DURATION]: {
      used: toMinutes(usage.elapsedSeconds),
      limit:
        limits?.maxDurationSeconds !== undefined
          ? toMinutes(limits.maxDurationSeconds)
          : undefined,
      unit: AGENT_AUTO_COPY.unitMinutes,
    },
    [AGENT_BUDGET_DIMENSION.OUTPUT]: {
      used: toMegabytes(usage.outputBytes),
      limit:
        limits?.maxOutputBytes !== undefined
          ? toMegabytes(limits.maxOutputBytes)
          : undefined,
      unit: AGENT_AUTO_COPY.unitMegabytes,
    },
  }
}

/**
 * 预算水位行（顺序固定：轮次 → 工具调用 → token → 时长 → 输出）。
 * 未启用（limit 缺省或 ≤0）的维度保留行但只显示已用，比例不参与「最高」判定。
 */
export function autoBudgetRows(
  usage: AgentAutoUsage,
  limits: AgentRunBudget | undefined
): AutoBudgetRow[] {
  const values = dimensionValues(usage, limits)
  return Object.values(AGENT_BUDGET_DIMENSION).map((dimension) => {
    const { used, limit, unit } = values[dimension]
    const enabled = limit !== undefined && limit > 0
    const ratio = enabled ? used / limit : undefined
    return {
      dimension,
      label: AGENT_BUDGET_DIMENSION_LABELS[dimension],
      used,
      limit: enabled ? limit : undefined,
      ratio,
      text: enabled ? `${used} / ${limit} ${unit}` : `${used} ${unit}`,
    }
  })
}

/** 当前最高消耗比（优先取服务端 ratio；缺失时按行计算，全未启用为 0） */
export function autoMaxRatio(
  progress:
    | Pick<AgentAutoProgress, 'ratio' | 'usage' | 'limits'>
    | null
    | undefined
): number {
  if (!progress) return 0
  if (Number.isFinite(progress.ratio) && progress.ratio > 0) return progress.ratio
  const ratios = autoBudgetRows(progress.usage, progress.limits)
    .map((row) => row.ratio)
    .filter((value): value is number => value !== undefined)
  return ratios.length > 0 ? Math.max(...ratios) : 0
}

/** 预算水位一行摘要（时间线 detail：「轮次 3/60 · 工具 5/120 · 已用 8%」） */
export function formatAutoUsageSummary(
  progress: Pick<AgentAutoProgress, 'usage' | 'limits' | 'ratio'>
): string {
  const rows = autoBudgetRows(progress.usage, progress.limits)
    .filter((row) => row.limit !== undefined)
    .slice(0, 2)
    .map((row) => `${row.label} ${row.text}`)
  rows.push(`已用 ${formatPercent(autoMaxRatio(progress))}`)
  return rows.join(' · ')
}

/** 暂停原因 → 面板标题下的说明文案 */
export function pauseReasonText(
  reason: AgentRunPauseReason | undefined,
  policyFailures?: number
): string {
  if (reason === AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD) {
    return AGENT_AUTO_COPY.pausedBudget
  }
  if (reason === AGENT_RUN_PAUSE_REASON.CONSECUTIVE_TOOL_FAILURES) {
    return policyFailures !== undefined && policyFailures > 0
      ? `连续 ${policyFailures} 次工具失败，已暂停自动重试`
      : AGENT_AUTO_COPY.pausedFailures
  }
  return AGENT_AUTO_COPY.pausedUnknown
}

/** Auto run 判定（run 快照的 mode；缺省不是 Auto） */
export function isAutoRun(
  run: AgentRun | null | undefined
): run is AgentRun {
  return run?.mode === AGENT_RUN_MODE.AUTO
}

/** Auto 终态分类（进度面板收口样式与文案据此分流） */
export const AUTO_TERMINAL_KIND = {
  SUCCEEDED: 'succeeded',
  BUDGET_EXCEEDED: 'budget_exceeded',
  CIRCUIT_BREAK: 'circuit_break',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const

export type AutoTerminalKind =
  (typeof AUTO_TERMINAL_KIND)[keyof typeof AUTO_TERMINAL_KIND]

/**
 * Auto 终态分类：只有 SUCCEEDED 算成功；BUDGET_EXCEEDED 单列；
 * FAILED 且错误码为 CONSECUTIVE_TOOL_FAILURES 判熔断（§9.3 连续失败熔断），
 * 其余 FAILED 仍是失败。非终态返回 null。
 */
export function autoTerminalKind(
  run: AgentRun | null | undefined
): AutoTerminalKind | null {
  if (!run) return null
  switch (run.status) {
    case AGENT_RUN_STATUS.SUCCEEDED:
      return AUTO_TERMINAL_KIND.SUCCEEDED
    case AGENT_RUN_STATUS.BUDGET_EXCEEDED:
      return AUTO_TERMINAL_KIND.BUDGET_EXCEEDED
    case AGENT_RUN_STATUS.CANCELLED:
      return AUTO_TERMINAL_KIND.CANCELLED
    case AGENT_RUN_STATUS.FAILED:
      return run.error?.includes(AGENT_AUTO_ERROR_CODE.CONSECUTIVE_TOOL_FAILURES)
        ? AUTO_TERMINAL_KIND.CIRCUIT_BREAK
        : AUTO_TERMINAL_KIND.FAILED
    default:
      return null
  }
}

/** 终态文案（标题 + 说明）；非终态返回 null */
export function autoTerminalCopy(
  kind: AutoTerminalKind | null
): { title: string; description: string } | null {
  switch (kind) {
    case AUTO_TERMINAL_KIND.SUCCEEDED:
      return { title: AGENT_AUTO_COPY.finishedTitle, description: '' }
    case AUTO_TERMINAL_KIND.BUDGET_EXCEEDED:
      return {
        title: AGENT_AUTO_COPY.budgetExceededTitle,
        description: AGENT_AUTO_COPY.budgetExceededDesc,
      }
    case AUTO_TERMINAL_KIND.CIRCUIT_BREAK:
      return {
        title: AGENT_AUTO_COPY.circuitTitle,
        description: AGENT_AUTO_COPY.circuitDesc,
      }
    case AUTO_TERMINAL_KIND.FAILED:
      return { title: AGENT_AUTO_COPY.failedTitle, description: '' }
    case AUTO_TERMINAL_KIND.CANCELLED:
      return { title: AGENT_AUTO_COPY.cancelledTitle, description: '' }
    default:
      return null
  }
}

/** 进度阶段文案（auto_step.phase） */
export function autoPhaseText(progress: AgentAutoProgress | null): string {
  switch (progress?.phase) {
    case 'resume':
      return AGENT_AUTO_COPY.phaseResume
    case 'continue':
      return AGENT_AUTO_COPY.phaseContinue
    default:
      return AGENT_AUTO_COPY.phaseStep
  }
}

/**
 * 气泡级 Auto 终态文案：Auto run 的收口不复用通用「Agent 运行失败，请重试」
 * （P3-5），与进度面板同一套终态口径；正文已有内容时由调用方保留。
 */
export function autoTerminalMessageText(
  kind: AutoTerminalKind | null
): string | null {
  const copy = autoTerminalCopy(kind)
  if (!copy) return null
  return copy.description ? `${copy.title}。${copy.description}` : copy.title
}
