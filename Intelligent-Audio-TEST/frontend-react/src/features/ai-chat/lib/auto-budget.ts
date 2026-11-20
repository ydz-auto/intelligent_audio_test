/**
 * Auto 预算草稿（features 层；INT-2474 §9.4）。
 *
 * 界面用字符串草稿（受控输入），提交前转成领域预算对象：
 * - 空串 = 用服务端默认（不覆盖该维度）；
 * - 只接受正整数：0 / 负数 / 小数 / 非数字都视为非法，**不静默截断**；
 *   非法项在输入框下方标红，且不进入请求体（后端对未知/非法预算直接 400，
 *   前端先把不可能成立的输入拦住）；
 * - 时长按分钟录入 → 秒；输出按 MB 录入 → 字节。
 *
 * 预算允许放宽（§9.4 修订）：这里不做上限校验（Auto 可在服务端默认之上上调，
 * 消耗用户自己的 token），只拦非正整数；上限 / 默认值口径由服务端下发。
 */
import {
  AGENT_AUTO_COPY,
  AGENT_BUDGET_DIMENSION_LABELS,
  type AgentAutoBudgetDefaults,
  type AgentRunBudget,
} from '@/domain/models/agent'
import { formatNumber } from '@/lib/format'

/** 五个预算维度的输入草稿（字符串；供受控输入原样回显） */
export interface AutoBudgetDraft {
  maxRounds: string
  maxToolCalls: string
  maxTokens: string
  maxDurationMinutes: string
  maxOutputMegabytes: string
}

export const EMPTY_AUTO_BUDGET_DRAFT: AutoBudgetDraft = {
  maxRounds: '',
  maxToolCalls: '',
  maxTokens: '',
  maxDurationMinutes: '',
  maxOutputMegabytes: '',
}

/** 输入的解析结果：undefined=留空（不收紧），null=非法 */
export type ParsedBudgetField = number | undefined | null

const SECONDS_PER_MINUTE = 60
const BYTES_PER_MEGABYTE = 1024 * 1024

/** 单个字段：空串 → undefined；正整数 → 数值；其余 → null（非法） */
export function parseBudgetField(text: string): ParsedBudgetField {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  if (!/^\d+$/.test(trimmed)) return null
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value <= 0 || !Number.isSafeInteger(value)) return null
  return value
}

/** 领域预算 → 草稿（分钟 / MB 由秒 / 字节换算；无值显示为空） */
export function toAutoBudgetDraft(budget: AgentRunBudget | undefined): AutoBudgetDraft {
  const numberText = (value: number | undefined): string =>
    value !== undefined && value > 0 ? String(value) : ''
  return {
    maxRounds: numberText(budget?.maxRounds),
    maxToolCalls: numberText(budget?.maxToolCalls),
    maxTokens: numberText(budget?.maxTokens),
    maxDurationMinutes: numberText(
      budget?.maxDurationSeconds !== undefined
        ? Math.round(budget.maxDurationSeconds / SECONDS_PER_MINUTE)
        : undefined
    ),
    maxOutputMegabytes: numberText(
      budget?.maxOutputBytes !== undefined
        ? Math.round(budget.maxOutputBytes / BYTES_PER_MEGABYTE)
        : undefined
    ),
  }
}

/** 每个字段的非法标记（供输入框标红；空串不算非法） */
export function invalidBudgetFields(draft: AutoBudgetDraft): Set<keyof AutoBudgetDraft> {
  const invalid = new Set<keyof AutoBudgetDraft>()
  for (const key of Object.keys(draft) as Array<keyof AutoBudgetDraft>) {
    if (parseBudgetField(draft[key]) === null) invalid.add(key)
  }
  return invalid
}

/**
 * 草稿 → 请求预算：只带合法且非空的维度；全部留空时返回 undefined
 * （请求体不带 budget，完全用服务端默认）。
 */
export function buildAutoBudget(draft: AutoBudgetDraft): AgentRunBudget | undefined {
  const rounds = parseBudgetField(draft.maxRounds)
  const toolCalls = parseBudgetField(draft.maxToolCalls)
  const tokens = parseBudgetField(draft.maxTokens)
  const minutes = parseBudgetField(draft.maxDurationMinutes)
  const megabytes = parseBudgetField(draft.maxOutputMegabytes)

  const budget: AgentRunBudget = {
    maxRounds: typeof rounds === 'number' ? rounds : undefined,
    maxToolCalls: typeof toolCalls === 'number' ? toolCalls : undefined,
    maxTokens: typeof tokens === 'number' ? tokens : undefined,
    maxDurationSeconds:
      typeof minutes === 'number' ? minutes * SECONDS_PER_MINUTE : undefined,
    maxOutputBytes:
      typeof megabytes === 'number' ? megabytes * BYTES_PER_MEGABYTE : undefined,
  }
  return Object.values(budget).some((value) => value !== undefined)
    ? budget
    : undefined
}

/** 两份预算是否等价（只比较显式给出的维度；供外部同步判断是否覆盖草稿） */
export function budgetsEqual(
  left: AgentRunBudget | undefined,
  right: AgentRunBudget | undefined
): boolean {
  const keys: Array<keyof AgentRunBudget> = [
    'maxRounds',
    'maxToolCalls',
    'maxTokens',
    'maxDurationSeconds',
    'maxOutputBytes',
  ]
  return keys.every((key) => (left?.[key] ?? undefined) === (right?.[key] ?? undefined))
}

/**
 * 服务端默认值 → 展示文案（例：「服务端默认（留空生效）：轮次 60 · 工具调用 120 ·
 * token 4×上下文窗口 · 时长 30 分钟 · 输出 20MB」）。
 *
 * maxTokens 为 0 表示按上下文窗口派生（倍数来自服务端）；缺省 / 0 的维度跳过。
 */
export function formatAutoBudgetDefaults(defaults: AgentAutoBudgetDefaults): string {
  const { budget, tokenMultiplier } = defaults
  const parts: string[] = []
  const labels = AGENT_BUDGET_DIMENSION_LABELS
  if (budget.maxRounds) {
    parts.push(`${labels.maxRounds} ${formatNumber(budget.maxRounds)}`)
  }
  if (budget.maxToolCalls) {
    parts.push(`${labels.maxToolCalls} ${formatNumber(budget.maxToolCalls)}`)
  }
  parts.push(
    budget.maxTokens && budget.maxTokens > 0
      ? `${labels.maxTokens} ${formatNumber(budget.maxTokens)}`
      : `${labels.maxTokens} ${tokenMultiplier}${AGENT_AUTO_COPY.budgetTokenWindowUnit}`
  )
  if (budget.maxDurationSeconds) {
    const minutes = Math.round(budget.maxDurationSeconds / SECONDS_PER_MINUTE)
    parts.push(`${labels.maxDurationSeconds} ${minutes}${AGENT_AUTO_COPY.unitMinutes}`)
  }
  if (budget.maxOutputBytes) {
    const megabytes = Math.round(budget.maxOutputBytes / BYTES_PER_MEGABYTE)
    parts.push(`${labels.maxOutputBytes} ${megabytes}${AGENT_AUTO_COPY.unitMegabytes}`)
  }
  return `${AGENT_AUTO_COPY.budgetDefaultHintPrefix}：${parts.join(' · ')}`
}
