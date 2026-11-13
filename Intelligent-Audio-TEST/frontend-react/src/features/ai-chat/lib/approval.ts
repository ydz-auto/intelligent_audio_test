/**
 * 审批卡片展示辅助（interfaces 层 ai-chat/lib；INT-2472 审计返修 P3-2/3/4）。
 *
 * 后端 proposal 里的 `step_id` / `turn` / `decided_by` 是内部字段：
 * - `turn` 从 0 起（run_orchestrator._next_turn），展示为 1 起；
 * - `step_id` 是内部步骤 UUID，用户无法使用，长 id 截断后展示；
 * - `decided_by` 是用户数字 id，只有当前用户能解析成「我」，其余显示「其他用户」。
 */

/** 步骤 id 截断后保留的字符数（UUID 只展示前 8 位） */
const STEP_ID_VISIBLE_LENGTH = 8

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
