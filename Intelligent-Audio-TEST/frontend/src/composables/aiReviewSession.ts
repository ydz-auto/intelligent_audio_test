/**
 * AI 复核会话（19 规范 §5.2/§5.3/§5.4/§5.5）——灵犀Agent 复核会话状态机（应用层 composable）。
 *
 * 独立会话 scope：本会话消息不进全局主会话（iatp:ai-chat:v1:messages），
 * 复核会话数据为组件内局部 state（关闭 Dialog 即释放；对应「独立 localStorage 键
 * iatp:ai-chat:v1:review:{taskId}:{caseId}」语义——持久化留给需要断点续传的场景）。
 * 供应商/模型配置复用主工作台（共享用户自配 LLM 供应商，§5.2 同引擎不同 scope）。
 *
 * 结论落位（§5.5）：
 * - 保存 → POST /tasks/results/ai-review（{result_ids, dimension_ids?, force?}）→ 轮询历史至 completed
 * - 采纳 → 打开 §3.2 复核弹窗预填 AI 判定 → 人工确认 → 单次 adopt（POST /ai-review/{id}/adopt，
 *   后端复用 apply_review 落 test_result_reviews，前端不补调 /tasks/results/review，防双写留痕）
 * - 驳回 → POST /ai-review/{id}/reject（原判定不变，记录标记已驳回备查）
 */
import { computed, ref } from 'vue'
import type { ChatMessage } from '@/domain/model/aiChat'
import { MESSAGE_STATUS } from '@/domain/constants/aiChat'
import { AI_REVIEW_CHAT_COPY, AI_REVIEW_RECORD_COPY } from '@/domain/constants/aiReviewSession'
import { useAiChatStore } from '@/store/aiChatStore'
import { llmProviderApi } from '@/infrastructure/api/llmProviderApi'
import { tasksApi } from '@/infrastructure/api/tasksApi'
import {
  requestAiReview,
  fetchAiReviewHistory,
  adoptAiReview,
  rejectAiReview,
} from '@/infrastructure/api/reviewAiApi'
import type { AiReviewRecord } from '@/domain/model/review'
import { useModalControl, MODAL_TYPES } from '@/composables/modal/useModal'
import { useNotification } from '@/composables/modal/useNotification'

/** 复核对象结果行（设备×结果；§5.3 上下文预填） */
export interface AiReviewSessionResult {
  id: string | number
  deviceName?: string | null
  apiName?: string | null
  executionStatus?: string | null
  evaluationStatus?: string | null
  reviewed?: boolean
  dimensions?: Array<{ name?: string; score?: number | string }>
}

/** 复核上下文（§5.3 契约，前端聚合真实数据） */
export interface AiReviewContext {
  taskId: number
  caseId: string
  caseName: string
  /** 设备×结果列表（真实 GET /tasks/{taskId}/cases/{caseId}/results） */
  results: AiReviewSessionResult[]
  /** 低分维度摘要（设备×维度表：score < 60 的维度名，默认复核维度） */
  lowDimensionText: string
  /** LLM 评语摘要（voice_llm evaluation.reasoning / llm_judge 维度分） */
  llmCommentText: string
  /** 已有 AI 复核结论（真实 GET ai-review-history 按 result_id 过滤） */
  existingRecord: AiReviewRecord | null
}

const STREAM_CHUNK_MS = 40
const STREAM_CHUNK_SIZE = 12
const POLL_INTERVAL_MS = 3000
const POLL_MAX_ATTEMPTS = 20

function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 复核专用系统提示（不注入杜撰报告事实；上下文由首条 assistant 结构化消息承载） */
const REVIEW_SYSTEM_PROMPT =
  '你是智能音频测试平台的灵犀Agent，正在对一条测试用例的评估结果进行事后复核。' +
  '基于复核对象、设备×结果、维度分数与 LLM 评语独立分析，给出复核通过/不通过/存疑结论 + 置信度 + 理由。' +
  '回答简洁专业，不确定的信息不要编造。'

/** 复核上下文 → 文本行（§5.3：注入首条 assistant + 用于 LLM 历史） */
function buildContextText(ctx: AiReviewContext): string {
  const parts = [
    `复核对象：${ctx.caseName}（${ctx.caseId}）`,
    `设备×结果：${ctx.results.length} 条`,
  ]
  if (ctx.lowDimensionText) parts.push(`低分维度：${ctx.lowDimensionText}`)
  if (ctx.llmCommentText) parts.push(`LLM 评语：${ctx.llmCommentText}`)
  if (ctx.existingRecord) {
    const time = ctx.existingRecord.createdAt ? new Date(ctx.existingRecord.createdAt).toLocaleString('zh-CN') : ''
    parts.push(`已有 AI 复核结论：${ctx.existingRecord.verdict}（${time}）`)
  }
  return parts.join('｜')
}

/** 设备×维度表 → 低分维度摘要（score < 0.6，对齐 React aiReviewDialog lowScoreDim 口径 0-1 标度） */
function summarizeLowDimensions(results: AiReviewSessionResult[]): string {
  const hits: string[] = []
  for (const r of results) {
    for (const d of r.dimensions ?? []) {
      const score = typeof d.score === 'number' ? d.score : Number(d.score ?? NaN)
      if (Number.isFinite(score) && score < 0.6) {
        hits.push(`${r.deviceName ?? r.apiName ?? '设备'}/${d.name ?? '维度'}（${score}）`)
      }
    }
  }
  return hits.slice(0, 4).join('、')
}

/** LLM 评语摘要（voice_llm evaluation.reasoning 等，取首条结果的首段） */
function summarizeLlmComment(results: AiReviewSessionResult[]): string {
  for (const r of results) {
    if (r.dimensions) {
      for (const d of r.dimensions) {
        if (d.name && d.name.toLowerCase().includes('llm')) {
          return String(d.score ?? '') || ''
        }
      }
    }
  }
  return ''
}

export function useAiReviewSession(options: {
  taskId: number
  caseId: string
  caseName?: string
  /** 发起对象（用例执行结果行；缺省时组件内部经 GET /results 拉取） */
  results?: AiReviewSessionResult[]
  /** 采纳/驳回落位成功后通知父级（刷新复核标记/统计） */
  onAdopted?: () => void
}) {
  const { taskId, caseId, caseName } = options
  const chatStore = useAiChatStore()
  const modalControl = useModalControl()
  const notification = useNotification()

  // ===== 会话状态（独立 scope，关闭即释放） =====
  const phase = ref<'loading' | 'ready' | 'saving' | 'saved'>('loading')
  const messages = ref<ChatMessage[]>([])
  const isGenerating = ref(false)
  const context = ref<AiReviewContext | null>(null)
  const existingRecord = ref<AiReviewRecord | null>(null)
  const savedRecord = ref<AiReviewRecord | null>(null)
  const errorText = ref('')

  let runId: number | null = null
  let abortController: AbortController | null = null
  const timers: ReturnType<typeof setTimeout>[] = []
  let pollTimer: ReturnType<typeof setTimeout> | null = null

  function cancelTimers(): void {
    timers.forEach((id) => clearTimeout(id))
    timers.length = 0
  }

  /** 是否有可保存的对话结论（最后一条 assistant 已完成 = Agent 已给出结论，§5.4） */
  const canSave = computed(() => {
    if (phase.value === 'saving') return false
    const last = messages.value[messages.value.length - 1]
    return !!last && last.from === 'assistant' && last.status === MESSAGE_STATUS.COMPLETE
  })

  // ===== 上下文装配（§5.3：真实数据） =====

  async function assembleContext(): Promise<AiReviewContext> {
    let results: AiReviewSessionResult[] = options.results ?? []
    let detailLlmComment = ''
    try {
      if (results.length === 0) {
        const data = await tasksApi.getCaseResults(taskId, caseId)
        results = (data?.results ?? []).map((r: any) => ({
          id: r.id,
          deviceName: r.deviceName ?? null,
          apiName: r.apiName ?? null,
          executionStatus: r.executionStatus ?? null,
          evaluationStatus: r.evaluationStatus ?? null,
          reviewed: Boolean(r.reviewed),
          dimensions: (r.dimensions ?? []).map((d: any) => ({ name: d.name, score: d.score })),
        }))
      }
      // 维度分兜底：用例详情设备×维度表（低分维度识别）
      if (results.every((r) => (r.dimensions?.length ?? 0) === 0)) {
        const detail = await tasksApi.getCaseDetail(taskId, caseId)
        detailLlmComment = extractLlmCommentFromDetail(detail)
      }
    } catch {
      // 上下文装配失败不阻塞会话：保留传入/空结果，会话区可继续追问
    }

    const primaryId = results[0]?.id
    let existing: AiReviewRecord | null = null
    if (primaryId !== undefined) {
      try {
        const history = await fetchAiReviewHistory(taskId, { resultId: primaryId })
        existing = history.find((r) => r.status === 'completed' || r.status === 'running') ?? null
      } catch {
        existing = null
      }
    }

    return {
      taskId,
      caseId,
      caseName: caseName ?? `用例 ${caseId}`,
      results,
      lowDimensionText: summarizeLowDimensions(results),
      llmCommentText: summarizeLlmComment(results) || detailLlmComment,
      existingRecord: existing,
    }
  }

  function extractLlmCommentFromDetail(detail: any): string {
    const algos = detail?.algorithmResults ?? []
    for (const a of algos) {
      const name = String(a?.algorithmName ?? a?.name ?? '')
      if (name.toLowerCase().includes('llm')) {
        const reasoning = a?.resultData?.reasoning ?? a?.resultData?.output ?? a?.value ?? ''
        return typeof reasoning === 'string' ? reasoning.slice(0, 120) : ''
      }
    }
    return ''
  }

  /** 打开复核会话：装配真实上下文 → 首条 assistant 摘要卡 + 首条用户指令 */
  async function initialize(): Promise<void> {
    phase.value = 'loading'
    errorText.value = ''
    try {
      const ctx = await assembleContext()
      context.value = ctx
      existingRecord.value = ctx.existingRecord

      const contextKey = createId('assistant')
      const userKey = createId('user')
      messages.value = [
        {
          key: contextKey,
          from: 'assistant',
          versions: [{ id: `${contextKey}-v1`, content: buildContextText(ctx) }],
          createdAt: Date.now(),
          status: MESSAGE_STATUS.COMPLETE,
        },
        {
          key: userKey,
          from: 'user',
          versions: [{ id: `${userKey}-v1`, content: AI_REVIEW_CHAT_COPY.initialUserPrompt }],
          createdAt: Date.now(),
          status: MESSAGE_STATUS.COMPLETE,
        },
      ]
      phase.value = 'ready'
    } catch (e: any) {
      errorText.value = e?.message || '复核上下文加载失败'
      phase.value = 'ready'
    }
  }

  // ===== 对话 / 追问（复用主工作台供应商配置，§5.2） =====

  function buildChatHistory(text: string): Array<{ role: 'system' | 'user' | 'assistant'; content: string }> {
    const history: Array<{ role: 'system' | 'user' | 'assistant'; content: string }> = [
      { role: 'system', content: REVIEW_SYSTEM_PROMPT },
    ]
    for (const message of messages.value) {
      if (message.from !== 'user' && message.from !== 'assistant') continue
      if (message.status === 'loading' || message.status === 'error') continue
      const content = message.versions[message.versions.length - 1]?.content
      if (!content) continue
      history.push({
        role: message.from === 'user' ? 'user' : 'assistant',
        content,
      })
    }
    history.push({ role: 'user', content: text })
    return history
  }

  function patch(key: string, partial: Partial<ChatMessage>): void {
    messages.value = messages.value.map((m) => (m.key === key ? { ...m, ...partial } : m))
  }

  function stop(): void {
    if (runId === null) return
    runId = null
    cancelTimers()
    abortController?.abort()
    abortController = null
    isGenerating.value = false
  }

  /** 发送追问：追加用户消息 + Agent 流式回复（对话结论卡标记在首轮回复上） */
  function sendFollowUp(text: string): void {
    const trimmed = text.trim()
    if (!trimmed || runId !== null) return
    const provider = chatStore.providers.find((p) => p.id === chatStore.config.providerId) ?? chatStore.defaultProvider
    if (!provider || !provider.baseUrl || !provider.apiKey) {
      errorText.value = AI_REVIEW_CHAT_COPY.noProviderChat
      return
    }
    const model = chatStore.config.modelId
    if (!model) {
      errorText.value = AI_REVIEW_CHAT_COPY.noModel
      return
    }
    const userKey = createId('user')
    const assistantKey = createId('assistant')
    const now = Date.now()
    messages.value = [
      ...messages.value,
      {
        key: userKey,
        from: 'user',
        versions: [{ id: `${userKey}-v1`, content: trimmed }],
        createdAt: now,
        status: MESSAGE_STATUS.COMPLETE,
      },
      {
        key: assistantKey,
        from: 'assistant',
        versions: [{ id: `${assistantKey}-v1`, content: '' }],
        createdAt: now,
        startedAt: now,
        status: MESSAGE_STATUS.LOADING,
      },
    ]
    isGenerating.value = true
    errorText.value = ''
    const currentRunId = Date.now()
    runId = currentRunId
    const isInterrupted = () => runId !== currentRunId

    const abort = new AbortController()
    abortController = abort

    void (async () => {
      try {
        const content = await llmProviderApi.sendChatCompletion({
          baseUrl: provider.baseUrl,
          apiKey: provider.apiKey,
          model,
          messages: buildChatHistory(trimmed),
          signal: abort.signal,
        })
        if (isInterrupted()) return

        let index = 0
        const partial: Partial<ChatMessage> = {
          versions: [{ id: `${assistantKey}-v1`, content: '' }],
          status: MESSAGE_STATUS.STREAMING,
        }
        patch(assistantKey, partial)
        const stream = () => {
          if (isInterrupted()) return
          index += STREAM_CHUNK_SIZE
          patch(assistantKey, { versions: [{ id: `${assistantKey}-v1`, content: content.slice(0, index) }] })
          if (index < content.length) {
            timers.push(setTimeout(stream, STREAM_CHUNK_MS))
          } else {
            patch(assistantKey, {
              status: MESSAGE_STATUS.COMPLETE,
              completedAt: Date.now(),
              durationMs: Date.now() - now,
            })
            runId = null
            abortController = null
            isGenerating.value = false
          }
        }
        timers.push(setTimeout(stream, 120))
      } catch (err) {
        if (isInterrupted()) return
        const message = err instanceof Error && err.message ? err.message : AI_REVIEW_CHAT_COPY.error
        patch(assistantKey, {
          versions: [{ id: `${assistantKey}-v1`, content: message }],
          status: MESSAGE_STATUS.ERROR,
          completedAt: Date.now(),
        })
        runId = null
        abortController = null
        isGenerating.value = false
      }
    })()
  }

  // ===== 结论落位（§5.5） =====

  function pollForRecord(resultId: number | string, attempt = 0): void {
    if (pollTimer) clearTimeout(pollTimer)
    if (attempt >= POLL_MAX_ATTEMPTS) {
      errorText.value = AI_REVIEW_RECORD_COPY.failed
      phase.value = 'saved'
      return
    }
    pollTimer = setTimeout(async () => {
      try {
        const history = await fetchAiReviewHistory(taskId, { resultId })
        const rec = history.find((r) => r.status === 'completed' || r.status === 'failed')
        if (rec) {
          savedRecord.value = rec
          phase.value = 'saved'
          notification.success(AI_REVIEW_RECORD_COPY.saved)
          return
        }
        pollForRecord(resultId, attempt + 1)
      } catch {
        pollForRecord(resultId, attempt + 1)
      }
    }, POLL_INTERVAL_MS)
  }

  /** 保存复核结论：POST /ai-review（force=已有结论时绕过幂等复用）→ 轮询历史至落位 */
  async function saveConclusion(): Promise<void> {
    if (!canSave.value) return
    const resultIds = context.value?.results.map((r) => Number(r.id)).filter((id) => id > 0)
    if (!resultIds || resultIds.length === 0) {
      errorText.value = '该用例无执行结果，无法发起复核'
      return
    }
    phase.value = 'saving'
    errorText.value = ''
    try {
      await requestAiReview(taskId, caseId, {
        resultIds,
        force: Boolean(existingRecord.value),
      })
      pollForRecord(resultIds[0])
    } catch (e: any) {
      errorText.value = e?.message || AI_REVIEW_RECORD_COPY.failed
      phase.value = 'ready'
    }
  }

  /** 采纳：打开 §3.2 复核弹窗预填 AI 判定 → 人工确认 → 单次 adopt（防双写留痕） */
  async function adoptConclusion(): Promise<void> {
    const record = savedRecord.value
    if (!record) return
    const suggestedEvaluation = record.verdict === 'passed'
      ? 'completed'
      : record.verdict === 'failed'
        ? 'failed'
        : undefined
    try {
      const res = await modalControl.open(MODAL_TYPES.RESULT_REVIEW, {
        title: '人工复核',
        taskId,
        caseName: context.value?.caseName,
        results: [{ resultId: record.resultId, executionStatus: undefined, evaluationStatus: suggestedEvaluation }],
        reviewHistory: [],
        preset: { evaluationStatus: suggestedEvaluation, comment: record.reasoning },
      }).catch(() => undefined)
      if (res) {
        await adoptAiReview(record.id, {
          executionStatus: res.executionStatus,
          evaluationStatus: res.evaluationStatus || suggestedEvaluation,
          comment: res.comment || record.reasoning,
        })
        notification.success(AI_REVIEW_RECORD_COPY.adoptedDone)
        options.onAdopted?.()
      }
    } catch (e: any) {
      errorText.value = e?.message || '采纳 AI 复核失败，请稍后重试'
    }
  }

  /** 驳回：POST /ai-review/{id}/reject（原判定不变，记录标记已驳回备查） */
  async function rejectConclusion(): Promise<void> {
    const record = savedRecord.value
    if (!record) return
    try {
      const updated = await rejectAiReview(record.id)
      savedRecord.value = updated
      notification.success(AI_REVIEW_RECORD_COPY.rejectedDone)
    } catch (e: any) {
      errorText.value = e?.message || '驳回 AI 复核失败，请稍后重试'
    }
  }

  /** 重置会话（关闭 Dialog 释放局部 state） */
  function reset(): void {
    stop()
    if (pollTimer) clearTimeout(pollTimer)
    cancelTimers()
    phase.value = 'loading'
    messages.value = []
    context.value = null
    existingRecord.value = null
    savedRecord.value = null
    errorText.value = ''
  }

  return {
    // state
    phase,
    messages,
    isGenerating,
    context,
    existingRecord,
    savedRecord,
    errorText,
    // computed
    canSave,
    // actions
    initialize,
    sendFollowUp,
    stop,
    saveConclusion,
    adoptConclusion,
    rejectConclusion,
    reset,
  }
}
