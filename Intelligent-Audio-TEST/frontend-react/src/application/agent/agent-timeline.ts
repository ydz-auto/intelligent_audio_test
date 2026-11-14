/**
 * Run 时间线归约（application 层；§12.2「审批卡 + Run 时间线」/ 拍板增补 3）。
 *
 * 时间线是**事件流的有序投影**：每条 entry 保留后端事件的 `sequence`，重连回放
 * 由 agent-run-store 的全局去重水位保证不重复（本模块不再做去重，只做归约与展示
 * 文案）。`message_delta` 按 message 聚合成一条（连写数十上百段正文不该刷屏），
 * 聚合条保留首条 sequence 与最新 lastSequence，排序口径与后端一致。
 *
 * 审批决策不产生 SSE 事件（后端只发 approval_required），决策人与时间由审批单
 * 行的 decided_by / decided_at 回填到对应时间线条目（applyApprovalToTimeline），
 * 时间线本身仍按事件 sequence 排列，不掺入前端本地序号。
 */
import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_STATUS,
  AGENT_AUTO_COPY,
  AGENT_EVENT_TYPE,
  AGENT_TOOL_LABELS,
  AGENT_TOOL_RISK_LABELS,
  type AgentApproval,
  type AgentApprovalStatus,
  type AgentRunEvent,
  type AgentToolRisk,
} from '@/domain/models/agent'

import {
  formatAutoUsageSummary,
  pauseReasonText,
} from './auto-progress'

/** 时间线条目类型（与事件类型一一对应，message_delta 聚合为 message） */
export const AGENT_TIMELINE_KIND = {
  RUN_STARTED: 'run_started',
  MESSAGE: 'message',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  APPROVAL: 'approval',
  CONTEXT_COMPACTED: 'context_compacted',
  /** Auto 每轮进度（INT-2474） */
  AUTO_STEP: 'auto_step',
  RUN_PAUSED: 'run_paused',
  RUN_RESUMED: 'run_resumed',
  RUN_FINISHED: 'run_finished',
  ERROR: 'error',
} as const

export type AgentTimelineKind =
  (typeof AGENT_TIMELINE_KIND)[keyof typeof AGENT_TIMELINE_KIND]

export interface AgentTimelineEntry {
  kind: AgentTimelineKind
  /** 后端事件严格递增序号（首条） */
  sequence: number
  /** 聚合条目的最新序号（普通条目等于 sequence） */
  lastSequence: number
  /** 事件时间戳（ISO；聚合条目保留首条时间） */
  at: string
  label: string
  detail?: string
  /** 工具 / 审批条目的状态（tool_result status、approval status 等） */
  status?: string
  risk?: AgentToolRisk
  toolCallId?: string
  approvalId?: string
  /** message_delta 聚合键与累计字数 */
  messageId?: string
  charCount?: number
  /** context_compacted 调试标记 */
  debug?: boolean
  /** Auto 步进序号 / 最高预算消耗比 / 产物数（INT-2474 时间线展示） */
  step?: number
  ratio?: number
  artifactCount?: number
  /** 审批决策人与时间（由 applyApprovalToTimeline 回填） */
  decidedBy?: number
  decidedAt?: string
}

const TOOL_RESULT_STATUS_LABELS: Record<string, string> = {
  SUCCEEDED: '成功',
  FAILED: '失败',
  CANCELLED: '已取消',
}

function toolLabel(tool: string | undefined): string {
  if (!tool) return '未知工具'
  return AGENT_TOOL_LABELS[tool] ?? tool
}

function riskLabel(risk: AgentToolRisk | undefined): string | undefined {
  return risk ? AGENT_TOOL_RISK_LABELS[risk] : undefined
}

function contextCompactedDetail(event: Extract<
  AgentRunEvent,
  { type: typeof AGENT_EVENT_TYPE.CONTEXT_COMPACTED }
>): string {
  const parts: string[] = []
  if (event.level) parts.push(`层级 ${event.level}`)
  if (
    event.tokenCountBefore !== undefined ||
    event.tokenCountAfter !== undefined
  ) {
    parts.push(
      `token ${event.tokenCountBefore ?? '?'} → ${event.tokenCountAfter ?? '?'}`
    )
  }
  if (event.droppedCount !== undefined) {
    parts.push(`裁剪 ${event.droppedCount} 条`)
  }
  return parts.join(' · ')
}

function toEntry(event: AgentRunEvent): AgentTimelineEntry {
  const base = {
    sequence: event.sequence,
    lastSequence: event.sequence,
    at: event.timestamp,
  }
  switch (event.type) {
    case AGENT_EVENT_TYPE.RUN_STARTED:
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.RUN_STARTED,
        label: '运行开始',
        detail: event.model ? `模型 ${event.model}` : undefined,
        status: event.status,
      }
    case AGENT_EVENT_TYPE.MESSAGE_DELTA:
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.MESSAGE,
        label: '回复生成',
        messageId: event.messageId,
        charCount: event.delta.length,
        detail: `${event.delta.length} 字`,
      }
    case AGENT_EVENT_TYPE.TOOL_CALL:
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.TOOL_CALL,
        label: `调用 ${toolLabel(event.tool)}`,
        detail: event.summary,
        risk: event.risk,
        toolCallId: event.toolCallId,
      }
    case AGENT_EVENT_TYPE.TOOL_RESULT:
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.TOOL_RESULT,
        label: `工具结果 · ${TOOL_RESULT_STATUS_LABELS[event.status] ?? event.status}`,
        detail: event.summary,
        status: event.status,
        toolCallId: event.toolCallId,
      }
    case AGENT_EVENT_TYPE.APPROVAL_REQUIRED: {
      const labels = [
        riskLabel(event.risk),
        event.expiresAt
          ? `${AGENT_APPROVAL_COPY.expiresAt} ${formatClock(event.expiresAt)}`
          : undefined,
      ].filter((item): item is string => Boolean(item))
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.APPROVAL,
        label: `等待审批：${toolLabel(event.tool)}`,
        detail: labels.join(' · '),
        risk: event.risk,
        status: AGENT_APPROVAL_STATUS.PENDING,
        approvalId: event.approvalId,
        toolCallId: event.toolCallId,
      }
    }
    case AGENT_EVENT_TYPE.CONTEXT_COMPACTED:
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.CONTEXT_COMPACTED,
        label: '上下文压缩',
        detail: contextCompactedDetail(event),
        status: event.level,
        debug: event.debug === true,
      }
    case AGENT_EVENT_TYPE.AUTO_STEP:
      // 每轮一条：步序号 + 计划/目标摘要 + 预算水位（详情面板另给完整五维）
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.AUTO_STEP,
        label: `Auto 第 ${event.progress.step} 步`,
        detail: [event.progress.plan || event.progress.goal, formatAutoUsageSummary(event.progress)]
          .filter((item): item is string => Boolean(item && item.trim()))
          .join(' · '),
        status: event.progress.phase,
        step: event.progress.step,
        ratio: event.progress.ratio,
        artifactCount: event.progress.artifactCount,
      }
    case AGENT_EVENT_TYPE.RUN_PAUSED: {
      const reasonText = pauseReasonText(
        event.pause.reason,
        event.pause.policy?.consecutiveFailures
      )
      const usageText =
        event.pause.usage && event.pause.limits
          ? formatAutoUsageSummary({
              usage: event.pause.usage,
              limits: event.pause.limits,
              ratio: event.pause.ratio ?? 0,
            })
          : ''
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.RUN_PAUSED,
        label: AGENT_AUTO_COPY.pausedTitle,
        detail: [reasonText, usageText]
          .filter((item) => Boolean(item))
          .join(' · '),
        status: event.pause.reason,
      }
    }
    case AGENT_EVENT_TYPE.RUN_RESUMED:
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.RUN_RESUMED,
        label: '用户确认继续',
        // 预算暂停点被确认后同一暂停点不再触发（§9.4），在时间线里标明
        detail: event.ackedBudgetPause ? '已确认预算暂停点' : undefined,
        status: event.pauseReason,
      }
    case AGENT_EVENT_TYPE.RUN_FINISHED:
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.RUN_FINISHED,
        label: '运行结束',
        // 终态（已完成 / 失败 / 已取消…）由条目徽标展示，detail 只留错误原因，
        // 不再重复「运行结束 · 已完成」（INT-2472 审计 P3-6）
        detail: event.error,
        status: event.status,
      }
    case AGENT_EVENT_TYPE.ERROR: {
      const prefix = event.errorCode ? `${event.errorCode} · ` : ''
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.ERROR,
        label: event.recoverable ? '上游中断（可续传）' : '运行错误',
        detail: `${prefix}${event.errorMessage}`,
        status: event.recoverable ? 'RECOVERABLE' : 'FAILED',
      }
    }
    default:
      // 未识别事件类型在 DTO 层已丢弃；这里兜底返回「未知事件」而不是静默改写顺序
      return {
        ...base,
        kind: AGENT_TIMELINE_KIND.ERROR,
        label: '未知事件',
        status: 'UNKNOWN',
      }
  }
}

/**
 * 追加一条事件到时间线（返回新数组，不改入参）。
 * - 连续的同 message 增量聚合成一条：首条 sequence 不动，lastSequence / 字数 / detail 累加；
 * - 其他事件按到达顺序追加；顺序由上游去重水位保证与后端 sequence 一致。
 */
export function appendTimelineEntry(
  entries: readonly AgentTimelineEntry[],
  event: AgentRunEvent
): AgentTimelineEntry[] {
  const entry = toEntry(event)
  if (entry.kind === AGENT_TIMELINE_KIND.MESSAGE) {
    const last = entries[entries.length - 1]
    if (
      last &&
      last.kind === AGENT_TIMELINE_KIND.MESSAGE &&
      last.messageId === entry.messageId
    ) {
      const charCount = (last.charCount ?? 0) + (entry.charCount ?? 0)
      const next: AgentTimelineEntry = {
        ...last,
        lastSequence: entry.lastSequence,
        charCount,
        detail: `${charCount} 字`,
      }
      return [...entries.slice(0, -1), next]
    }
  }
  return [...entries, entry]
}

function approvalStatusLabel(status: AgentApprovalStatus): string {
  switch (status) {
    case AGENT_APPROVAL_STATUS.APPROVED:
      return AGENT_APPROVAL_COPY.approved
    case AGENT_APPROVAL_STATUS.REJECTED:
      return AGENT_APPROVAL_COPY.rejected
    case AGENT_APPROVAL_STATUS.EXPIRED:
      return AGENT_APPROVAL_COPY.expired
    default:
      return AGENT_APPROVAL_COPY.pending
  }
}

/**
 * 把审批单最新状态（决策人 / 时间）回填到对应时间线条目。
 * 决策不产生事件，因此不改 sequence，只更新条目的 status 与展示文案。
 */
export function applyApprovalToTimeline(
  entries: AgentTimelineEntry[],
  approval: AgentApproval
): AgentTimelineEntry[] {
  let changed = false
  const next = entries.map((entry) => {
    if (
      entry.kind !== AGENT_TIMELINE_KIND.APPROVAL ||
      entry.approvalId !== approval.id
    ) {
      return entry
    }
    changed = true
    // 决策人数字 id 属内部字段，交给界面层解析成「我 / 其他用户」（P3-4）；
    // 这里只保留状态与决策时间。
    const detail = [
      riskLabel(approval.proposal?.risk) ?? riskLabel(entry.risk),
      approvalStatusLabel(approval.status),
      approval.decidedAt
        ? `决策于 ${formatClock(approval.decidedAt)}`
        : undefined,
    ]
      .filter((item): item is string => Boolean(item))
      .join(' · ')
    return {
      ...entry,
      status: approval.status,
      decidedBy: approval.decidedBy,
      decidedAt: approval.decidedAt,
      detail,
    }
  })
  return changed ? next : entries
}

/** 时间线条目里的工具调用次数（与审批卡计数同源：tool_call 事件各算一次） */
export function countTimelineToolCalls(
  entries: readonly AgentTimelineEntry[]
): number {
  return entries.filter((entry) => entry.kind === AGENT_TIMELINE_KIND.TOOL_CALL)
    .length
}

/** ISO → 本地 HH:MM:SS（时间线与卡片共用；无效时间原样返回） */
export function formatClock(iso: string | undefined): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}
