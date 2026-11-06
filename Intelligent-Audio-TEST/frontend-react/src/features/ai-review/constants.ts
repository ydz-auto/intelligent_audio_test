/**
 * AI 复核会话文案与提示词（interfaces 层 features/ai-review；19 规范 §7 文案全量 + §5.3/§5.4）。
 * 灵犀Agent 复核会话为任务/用例级有界会话（§5.2）：对话由用户自配 LLM 供应商驱动（Demo），
 * 「保存复核结论」落位走真实后端端点（INT-800 done，非 Demo）——两者分离（§3.10/§5.6）。
 */
import type { AiReviewContext } from '@/domain/models/review'
import { aiConfidenceLabel, AI_VERDICT_LABELS } from '@/domain/models/review'

/** 首条用户指令（§5.3 预填可编辑） */
export const REVIEW_INITIAL_PROMPT =
  '请复核该用例的评估结果，给出复核通过/不通过/存疑结论 + 置信度 + 理由。'

/** 快捷追问 chips（§5.4：照 08 §3.4 Suggestion 语义，点击即发送） */
export const REVIEW_QUICK_PROMPTS = [
  '哪个维度失分最多？',
  '对比其他设备的表现',
  '给出逐设备复核意见',
] as const

/** 展开到 /ai-chat 预填指令（08 §3.7 URL 契约：/ai-chat?reviewTask={id}&reviewCase={caseId}） */
export function buildReviewExpandPrompt(taskId: number, caseId: string): string {
  return `请复核任务 #${taskId} 用例 ${caseId} 的评估结果，给出复核通过/不通过/存疑结论 + 置信度 + 理由。`
}

/** 复核上下文摘要 → 首条 assistant 消息（§5.3：结构化渲染，非裸 JSON） */
export function buildContextSummaryMessage(context: AiReviewContext): string {
  const deviceLabel =
    context.deviceResults
      .map((r) => r.deviceName ?? r.apiName ?? '—')
      .filter(Boolean)
      .join(' / ') || '—'
  const lowDim =
    context.dimensionScores.find((d) => d.score !== null && d.score < 0.6) ??
    context.dimensionScores[0]
  const lowDimText = lowDim
    ? `${lowDim.name}（${lowDim.score?.toFixed(2) ?? '—'}）`
    : '—'
  const lastReview = context.existingReviews.at(-1)
  const existingText = lastReview
    ? `${AI_VERDICT_LABELS[lastReview.verdict]}（${lastReview.createdAt ? formatReviewTime(lastReview.createdAt) : '—'}）`
    : '无'
  const reasoning =
    context.reasoning ??
    (context.existingReviews
      .filter((r) => r.status === 'completed' && r.reasoning)
      .at(-1)?.reasoning ??
      null)

  return [
    `**复核对象：** ${context.caseName}｜CaseId ${context.caseId}`,
    `**设备×结果：** ${context.deviceResults.length} 条｜${deviceLabel}`,
    `**低分维度：** ${lowDimText}`,
    `**LLM 评语：** ${reasoning || '无'}`,
    `**已有 AI 复核结论：** ${existingText}`,
  ].join('\n\n')
}

/** 复核上下文 → 复核会话系统提示（§5.3：作为系统提示 + 首条 assistant 摘要卡注入；只依据给定上下文判断） */
export function buildReviewSystemPrompt(context: AiReviewContext): string {
  const deviceLines =
    context.deviceResults.length > 0
      ? context.deviceResults
          .map(
            (r) =>
              `  - ${r.deviceName ?? r.apiName ?? '未知资源'}：执行 ${r.executionStatus ?? '—'}${r.lastReviewAction ? ` / 复核 ${r.lastReviewAction}` : ''}`
          )
          .join('\n')
      : '  - 无执行结果'
  const dimLines =
    context.dimensionScores.length > 0
      ? context.dimensionScores
          .map((d) => `  - ${d.name}：${d.score?.toFixed(2) ?? '—'}`)
          .join('\n')
      : '  - 无维度数据'
  const lastReview = context.existingReviews.at(-1)
  const existingText = lastReview
    ? `${AI_VERDICT_LABELS[lastReview.verdict]}（${lastReview.createdAt ? formatReviewTime(lastReview.createdAt) : '—'}）`
    : '无'

  return [
    '你是智能音频测试平台的灵犀Agent，正在执行 AI 复核。请仅依据下方复核上下文与平台数据独立分析，',
    '给出复核结论：复核通过 / 复核不通过 / 存疑 + 置信度 + 理由，并回答用户的追问；不确定的信息不要编造。',
    '',
    '【复核上下文】',
    `- 复核对象：${context.caseName}（CaseId ${context.caseId}）`,
    `- 所属任务：#${context.taskId}`,
    `- 当前评估状态：${context.evaluationStatus ?? '—'}`,
    `- 设备×结果：`,
    deviceLines,
    `- 评估维度分数：`,
    dimLines,
    `- 现有复核/评语：${context.reasoning ?? '无'}`,
    `- 已有 AI 复核结论：${existingText}`,
  ].join('\n')
}

/** 时间 → YYYY-MM-DD HH:mm（复核会话徽章/记录卡口径） */
export function formatReviewTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 置信度展示（0-1 → 百分比；复用 domain 口径） */
export { aiConfidenceLabel }
