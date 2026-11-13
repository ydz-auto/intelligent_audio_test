/**
 * 审批卡片展示辅助（interfaces 层 ai-chat/lib；INT-2472 审计返修 P3-2/3/4 /
 * P2 §9.4 批量粒度）。
 *
 * 后端 proposal 里的 `step_id` / `turn` / `decided_by` 是内部字段：
 * - `turn` 从 0 起（run_orchestrator._next_turn），展示为 1 起；
 * - `step_id` 是内部步骤 UUID，用户无法使用，长 id 截断后展示；
 * - `decided_by` 是用户数字 id，只有当前用户能解析成「我」，其余显示「其他用户」。
 *
 * §9.4：单次影响 >20 对象必须单条审批。后端当前一张审批单对应一次 tool call，
 * 因此由这里从提案参数里数出受影响对象，卡片据此强制逐项核对（不允许一次放行）。
 */

import {
  AGENT_APPROVAL_OBJECT_LIMIT,
  type AgentApproval,
} from '@/domain/models/agent'

/** 步骤 id 截断后保留的字符数（UUID 只展示前 8 位） */
const STEP_ID_VISIBLE_LENGTH = 8

/** 对象数组字段名（`device_ids` / `ids` / `body.task_ids`…） */
const ID_ARRAY_KEY = /(^|_)ids?$/i

/** 对象清单字段名（`devices` / `items` / `records`…；元素带 id 时计数） */
const OBJECT_LIST_KEY = /(^|_)(devices|tasks|cases|reports|items|records|objects)$/i

/** 递归扫描参数的最大深度（防止异常提案把扫描拖进深层嵌套） */
const MAX_SCAN_DEPTH = 6

/** 卡片上最多展示的对象标识数（逐项核对列表只用前 N 个，避免渲染超长列表） */
const MAX_TARGETS_SHOWN = 50

/** 对象标识字段候选（对象数组元素取 id / _id / key） */
const TARGET_ID_KEYS = ['id', '_id', 'key'] as const

/** 提案影响的对象清单（§9.4 批量审批粒度判定） */
export interface ApprovalTargetSummary {
  /** 受影响对象数：提案中对象数组的最大长度（无对象数组为 0） */
  count: number
  /** 参与统计的字段路径（如 `device_ids`、`body.task_ids`） */
  fields: string[]
  /** 对象标识样本（最多 MAX_TARGETS_SHOWN 个，供逐项核对） */
  targets: string[]
  /** 是否超过单次审批上限（>20 对象必须单条） */
  overLimit: boolean
}

type FoundList = { path: string; items: unknown[] }

function targetLabel(item: unknown): string {
  if (item === null || item === undefined) return '-'
  if (typeof item === 'string' || typeof item === 'number') return String(item)
  if (typeof item === 'object') {
    const record = item as Record<string, unknown>
    for (const key of TARGET_ID_KEYS) {
      const value = record[key]
      if (typeof value === 'string' || typeof value === 'number') {
        return String(value)
      }
    }
  }
  return JSON.stringify(item)
}

/** 对象数组：元素都是对象且带可展示标识（排除嵌套数组 / 原始值列表） */
function isObjectList(items: unknown[]): boolean {
  if (items.length === 0) return false
  return items.every(
    (item) =>
      item !== null &&
      typeof item === 'object' &&
      !Array.isArray(item) &&
      TARGET_ID_KEYS.some((key) => {
        const value = (item as Record<string, unknown>)[key]
        return typeof value === 'string' || typeof value === 'number'
      })
  )
}

function collectLists(
  value: unknown,
  path: string,
  depth: number,
  found: FoundList[]
): void {
  if (depth > MAX_SCAN_DEPTH) return
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const childPath = path ? `${path}.${key}` : key
    if (Array.isArray(child)) {
      if (ID_ARRAY_KEY.test(key) || (OBJECT_LIST_KEY.test(key) && isObjectList(child))) {
        found.push({ path: childPath, items: child })
      }
      continue
    }
    collectLists(child, childPath, depth + 1, found)
  }
}

/**
 * 数出提案一次影响的对象数（§9.4）：
 * - `*_ids` / `*_id` 数组按元素个数计；
 * - `devices` / `items` / `records` 一类对象数组（元素带 id）按对象个数计；
 * - 多个字段并存时取最大值（避免同一批对象在嵌套结构里被重复计数）。
 */
export function summarizeApprovalTargets(
  approval: Pick<AgentApproval, 'proposal'>
): ApprovalTargetSummary {
  const found: FoundList[] = []
  const args = approval.proposal?.arguments
  if (args) collectLists(args, '', 0, found)

  const matched = found.filter((item) => item.items.length > 0)
  const count = matched.reduce(
    (max, item) => Math.max(max, item.items.length),
    0
  )
  const primary =
    matched.find((item) => item.items.length === count) ?? null
  return {
    count,
    fields: matched.map((item) => item.path),
    targets: (primary?.items ?? [])
      .slice(0, MAX_TARGETS_SHOWN)
      .map(targetLabel),
    overLimit: count > AGENT_APPROVAL_OBJECT_LIMIT,
  }
}

/** 步骤 id → 可展示文案（缺失返回 null；过长截断，不直出内部 UUID） */
export function formatApprovalStepId(
  stepId: string | undefined
): string | null {
  const value = stepId?.trim()
  if (!value) return null
  return value.length > STEP_ID_VISIBLE_LENGTH
    ? `${value.slice(0, STEP_ID_VISIBLE_LENGTH)}…`
    : value
}

/** 轮次 → 可展示文案（后端 0 起；缺失返回 null，不显示「第 0 轮」） */
export function formatApprovalTurn(turn: number | undefined): string | null {
  if (turn === undefined || !Number.isFinite(turn)) return null
  return `第 ${turn + 1} 轮`
}

/**
 * 决策人 → 可展示文案：当前用户显示「我」；其他用户没有可解析的名称，
 * 显示「其他用户」而不是内部用户 id。决策人缺失返回 null。
 */
export function formatApprovalApprover(
  decidedBy: number | undefined,
  currentUserId: string | undefined
): string | null {
  if (decidedBy === undefined) return null
  if (currentUserId !== undefined && String(decidedBy) === currentUserId) {
    return '我'
  }
  return '其他用户'
}
