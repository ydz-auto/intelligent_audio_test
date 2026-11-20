/**
 * 审批卡片展示辅助（interfaces 层 ai-chat/lib；INT-2472 审计返修 P3-2/3/4 /
 * P2 §9.4 批量粒度 / INT-2573 §9.4.1 拆单批次）。
 *
 * 后端 proposal 里的 `step_id` / `turn` / `decided_by` 是内部字段：
 * - `turn` 从 0 起（run_orchestrator._next_turn），展示为 1 起；
 * - `step_id` 是内部步骤 UUID，用户无法使用，长 id 截断后展示；
 * - `decided_by` 是用户数字 id，只有当前用户能解析成「我」，其余显示「其他用户」。
 *
 * §9.4：单次影响 >20 对象必须单条审批。后端当前一张审批单对应一次 tool call，
 * 因此由这里从提案参数里数出受影响对象，卡片据此强制逐项核对（不允许一次放行）。
 *
 * §9.4.1（INT-2571 后端已拆单）：一次 tool call 影响 >20 对象时后端拆成 N 张单，
 * 同批共享 `batch_id`、按 `batch_index` 1..N 排序，执行是 all-or-nothing。
 * 这里负责把同批卡片聚成一组、给出「第 i/N 条」与批次状态口径。
 */

import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_OBJECT_LIMIT,
  AGENT_APPROVAL_STATUS,
  isApprovalExpired,
  type AgentApproval,
  type AgentApprovalObjectRef,
  type AgentApprovalStatus,
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

/** 单卡最多展示的对象 id 数（object_ref.ids 可能整批收窄后也很长） */
const MAX_OBJECT_REF_IDS_SHOWN = 5

/**
 * 是否属于拆单批次（§9.4.1：`batch_total > 1`）。
 * 旧单 / 缺字段按单张处理，渲染与改造前完全一致。
 */
export function isBatchedApproval(
  approval: Pick<AgentApproval, 'batchTotal'>
): boolean {
  return (approval.batchTotal ?? 1) > 1
}

/**
 * 批次状态口径（§9.4.1 第 5 条 all-or-nothing）：
 * - 任一单 REJECTED → 整批拒绝（后端把其余 PENDING 自动转 REJECTED）；
 * - 任一单 EXPIRED（含本地倒计时到点）→ 整批不执行；
 * - 仍有 PENDING → 本批等审批；
 * - 全部 APPROVED → 待执行。
 * 拒绝优先于过期，避免把「已拒绝」展示成「过期」。
 */
export function resolveApprovalBatchState(
  approvals: AgentApproval[],
  now: number = Date.now()
): AgentApprovalStatus {
  if (approvals.length === 0) return AGENT_APPROVAL_STATUS.PENDING
  const effective = approvals.map((approval) =>
    isApprovalExpired(approval, now)
      ? AGENT_APPROVAL_STATUS.EXPIRED
      : approval.status
  )
  const has = (status: AgentApprovalStatus) => effective.includes(status)
  if (has(AGENT_APPROVAL_STATUS.REJECTED)) {
    return AGENT_APPROVAL_STATUS.REJECTED
  }
  if (has(AGENT_APPROVAL_STATUS.EXPIRED)) {
    return AGENT_APPROVAL_STATUS.EXPIRED
  }
  if (has(AGENT_APPROVAL_STATUS.PENDING)) {
    return AGENT_APPROVAL_STATUS.PENDING
  }
  return AGENT_APPROVAL_STATUS.APPROVED
}

/** 批次状态 → 组头提示（§9.4.1：只有全批准才执行，任一拒绝 / 过期整批不执行） */
export function approvalBatchStateCopy(
  state: AgentApprovalStatus
): string {
  switch (state) {
    case AGENT_APPROVAL_STATUS.APPROVED:
      return AGENT_APPROVAL_COPY.batchAllApproved
    case AGENT_APPROVAL_STATUS.REJECTED:
      return AGENT_APPROVAL_COPY.batchRejected
    case AGENT_APPROVAL_STATUS.EXPIRED:
      return AGENT_APPROVAL_COPY.batchExpired
    default:
      return AGENT_APPROVAL_COPY.batchAllPending
  }
}

/** 单卡序号文案「本批第 i/N 条」；未拆单（N<=1）返回 null，不打扰旧单张 */
export function formatApprovalBatchIndex(
  batchIndex: number | undefined,
  batchTotal: number | undefined
): string | null {
  const total = batchTotal ?? 1
  if (total <= 1) return null
  if (batchIndex === undefined || !Number.isFinite(batchIndex)) return null
  return `${AGENT_APPROVAL_COPY.batchIndexPrefix} ${batchIndex}/${total} ${AGENT_APPROVAL_COPY.batchIndexSuffix}`
}

/**
 * object_ref → 单卡对象摘要（如 `testcase · c1, c2…（共 21 个）`）。
 * 非枚举范围 ids 为空：展示 kind + 「按范围执行」，不伪造数量。
 */
export function summarizeApprovalObjectRef(
  objectRef: AgentApprovalObjectRef | undefined
): string | null {
  if (!objectRef) return null
  if (objectRef.ids.length === 0) {
    return objectRef.kind
      ? `${objectRef.kind} · ${AGENT_APPROVAL_COPY.batchObjectRange}`
      : AGENT_APPROVAL_COPY.batchObjectRange
  }
  const shown = objectRef.ids.slice(0, MAX_OBJECT_REF_IDS_SHOWN).join(', ')
  const suffix =
    objectRef.ids.length > MAX_OBJECT_REF_IDS_SHOWN
      ? `…（共 ${objectRef.ids.length} 个）`
      : ''
  return objectRef.kind
    ? `${objectRef.kind} · ${shown}${suffix}`
    : `${shown}${suffix}`
}

/**
 * 本批对象数：优先 `proposal.object_count`（§9.4.1：每张单都带批次总数，
 * 非枚举范围计 1）；缺失时回退为各单 object_ref.ids 之和（全部单都有摘要才可信）。
 */
export function resolveApprovalBatchObjectCount(
  approvals: AgentApproval[]
): number | undefined {
  const counts = approvals
    .map((approval) => approval.proposal?.objectCount)
    .filter(
      (count): count is number =>
        typeof count === 'number' && Number.isFinite(count)
    )
  if (counts.length > 0) return Math.max(...counts)
  if (approvals.length > 0 && approvals.every((approval) => approval.objectRef)) {
    return approvals.reduce(
      (total, approval) => total + (approval.objectRef?.ids.length ?? 0),
      0
    )
  }
  return undefined
}

/** 审批面板的渲染块：单张原样渲染，拆单批次聚成一组（组头 + 逐张卡） */
export type ApprovalPanelBlock =
  | { kind: 'single'; approval: AgentApproval }
  | {
      kind: 'batch'
      batchId: string
      /** 本批总单数（batch_total，不是本块里的卡片数：已决卡可能在折叠区） */
      total: number
      /** 同批卡片，按 batchIndex 升序（§9.4.1） */
      approvals: AgentApproval[]
      /** 批次状态（组头 all-or-nothing 口径） */
      state: AgentApprovalStatus
      /** 本批对象数（缺省不展示，不伪造） */
      objectCount?: number
    }

/**
 * 把一组审批单切成「单张 / 批次」渲染块（保持输入顺序）：
 * 同 `batchId` 且 `batchTotal > 1` 的卡片聚成一个批次块，块内按 `batchIndex`
 * 升序排列；批次块落在该批第一张卡出现的位置。旧单张（无批次字段）原样透传，
 * 渲染与 INT-2472 完全一致。
 *
 * `context` 是本面板的全量审批单（含已决 / 过期）：批次状态与对象数必须按整批
 * 算 —— 待审批组里只剩 2 张、同批另一张已拒绝时，组头要显示「本批不执行」，
 * 不能因为已决卡被折叠就误报「本批全部批准后才执行」。
 */
export function groupApprovalBatches(
  approvals: AgentApproval[],
  now: number = Date.now(),
  context: AgentApproval[] = approvals
): ApprovalPanelBlock[] {
  const blocks: ApprovalPanelBlock[] = []
  const seenBatchIds = new Set<string>()
  for (const approval of approvals) {
    const batchId = approval.batchId
    if (!batchId || !isBatchedApproval(approval)) {
      blocks.push({ kind: 'single', approval })
      continue
    }
    if (seenBatchIds.has(batchId)) continue
    seenBatchIds.add(batchId)
    const members = approvals
      .filter((item) => item.batchId === batchId)
      .sort(
        (left, right) => (left.batchIndex ?? 1) - (right.batchIndex ?? 1)
      )
    const allMembers = context.filter((item) => item.batchId === batchId)
    const stateSource = allMembers.length > 0 ? allMembers : members
    blocks.push({
      kind: 'batch',
      batchId,
      total: stateSource[0]?.batchTotal ?? members.length,
      approvals: members,
      state: resolveApprovalBatchState(stateSource, now),
      objectCount: resolveApprovalBatchObjectCount(stateSource),
    })
  }
  return blocks
}

/** 批次组头文案：「本批 N 张单 · 对象 P 个 · <状态提示>」 */
export function formatApprovalBatchHeader(
  total: number,
  objectCount: number | undefined,
  state: AgentApprovalStatus
): string {
  const parts = [
    `${AGENT_APPROVAL_COPY.batchGroupPrefix} ${total} ${AGENT_APPROVAL_COPY.batchGroupUnit}`,
  ]
  if (objectCount !== undefined) {
    parts.push(
      `${AGENT_APPROVAL_COPY.batchObjectPrefix} ${objectCount} ${AGENT_APPROVAL_COPY.batchObjectUnit}`
    )
  }
  parts.push(approvalBatchStateCopy(state))
  return parts.join(' · ')
}
