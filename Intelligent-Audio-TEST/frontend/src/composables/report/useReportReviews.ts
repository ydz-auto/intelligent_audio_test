/**
 * 报告侧复核编排 —— 人工审核（真实接口）+ AI 复核（真实接口，INT-800 已落地，INT-1070 接线）
 *
 * 消费面：报告详情「具体用例卡片」（SpecificCaseComparisonComponent）。
 * 数据源：
 * - 报告级统计徽章：report.summaries[0].metadata.review_count（报告生成时快照）
 *   兜底 `GET /tasks/results/{task_id}/review-count`（task:read，真实）
 * - 用例级复核标记/明细：`GET /tasks/results/{task_id}/review-history`（真实，
 *   逐条含 test_case_id，按用例聚合）
 * - 双路径入口 A（跳来源任务复核，默认）：经 `GET /tasks/{task_id}/cases/{caseId}/results`
 *   溯源结果行 → 打开 §3.2 复核弹窗（ResultReviewModal）预填 → POST /tasks/results/review
 * - 路径 B（报告内直接复核）：§4.2 待后端立项 → 未落地，人工复核仅路径 A
 * - AI 复核：§4.3 状态机（待发起→执行中→已完成→已采纳/已驳回/待查），
 *   真实端点 POST /tasks/results/ai-review + GET /tasks/results/{task_id}/ai-review-history
 *   + POST /ai-review/{id}/adopt|reject（INT-800 done，INT-1068/INT-1070 接线）
 */
import { ref, computed, onUnmounted } from 'vue';
import { useModalControl, MODAL_TYPES } from '@/composables/modal/useModal';
import { useNotification } from '@/composables/modal/useNotification';
import { toUserErrorMessage, toUserErrorDetail } from '@/utils/errorMessage';
import { reviewApi } from '@/infrastructure/api/reviewApi';
import { tasksApi } from '@/infrastructure/api/tasksApi';
import type {
  ReviewHistoryItemDomain,
  AiReviewPhase,
  AiReviewRecord,
  ReviewSubmitPayload,
} from '@/domain/model/review';

/** 用例卡片复核态（驱动卡片 Badge / 明细 / 入口显隐） */
export interface CaseReviewState {
  /** 用例是否存在复核留痕（含复核，§4.1 未落地前无计数展示） */
  hasReview: boolean
  /** 该用例复核留痕条数 */
  count: number
  /** 该用例复核留痕明细（倒序：最新在前） */
  items: ReviewHistoryItemDomain[]
}

/** AI 复核运行态（§2.1 状态机） */
export interface AiReviewRun {
  phase: AiReviewPhase
  record: AiReviewRecord | null
  error: string
}

/** AI 复核历史轮询（§5.6：发起后后端异步复检，轮询至 completed/failed；每 3s 一次） */
const AI_REVIEW_POLL_INTERVAL_MS = 3000
/** 轮询上限（3s×20 ≈ 60s；后端复检通常 5s 内落位） */
const AI_REVIEW_POLL_MAX_ATTEMPTS = 20

export function useReportReviews(reportDataRef: () => any) {
  const modalControl = useModalControl()
  const notification = useNotification()

  /** 报告级复核统计（驱动报告头/总览徽章） */
  const reportReviewCount = ref(0)
  /** 用例级复核态（test_case_id → CaseReviewState） */
  const caseReviewMap = ref<Record<string, CaseReviewState>>({})
  /** 来源任务 id（task 报告取 report.taskId；无则空） */
  const sourceTaskId = ref<string | number>('')
  /** 加载中 / 错误 */
  const loadingReviews = ref(false)
  const reviewsError = ref('')
  /** AI 复核运行态（test_case_id → AiReviewRun） */
  const aiReviewMap = ref<Record<string, AiReviewRun>>({})
  /** AI 复核轮询定时器（test_case_id → timer；卸载/重置时清理） */
  const aiPollTimers = new Map<string, ReturnType<typeof setTimeout>>()

  /** 报告总复核条数（徽章展示用） */
  const totalReviewCount = computed(() => reportReviewCount.value)

  const caseIdsWithReview = computed(() =>
    Object.keys(caseReviewMap.value).filter((k) => caseReviewMap.value[k]?.hasReview),
  )

  function emptyAiRun(): AiReviewRun {
    return { phase: 'idle', record: null, error: '' }
  }

  /** 取用例 AI 复核运行态（不存在则初始化为 待发起） */
  function getAiRun(caseId: string): AiReviewRun {
    if (!aiReviewMap.value[caseId]) {
      aiReviewMap.value[caseId] = emptyAiRun()
    }
    return aiReviewMap.value[caseId]
  }

  /** 读取用例级复核态（caseItem.id = test_case_id） */
  function getCaseReview(caseId: string | number): CaseReviewState {
    return caseReviewMap.value[String(caseId)] ?? { hasReview: false, count: 0, items: [] }
  }

  /** 解析来源任务 id：优先 report.taskId；合并报告回退 summaries metadata.task_ids 首项 */
  function resolveSourceTaskId(report: any): string | number {
    if (report?.taskId && Number(report.taskId) > 0) return report.taskId
    const meta = report?.summaries?.[0]?.metadata
    if (Array.isArray(meta?.task_ids) && meta.task_ids.length > 0) return meta.task_ids[0]
    return ''
  }

  /**
   * 加载报告复核数据：
   * - 报告级徽章数（快照 metadata.review_count，缺省走 task review-count 真实端点）
   * - 来源任务复核历史 → 按 test_case_id 聚合用例级标记/明细
   */
  async function loadReportReviews(report: any) {
    if (!report) return
    sourceTaskId.value = resolveSourceTaskId(report)
    loadingReviews.value = true
    reviewsError.value = ''

    // 1. 报告级复核条数：优先快照（report_summaries.review_count）
    const snapshotCount = Number(report?.summaries?.[0]?.metadata?.review_count ?? 0)
    if (snapshotCount > 0) {
      reportReviewCount.value = snapshotCount
    } else if (sourceTaskId.value !== '') {
      try {
        reportReviewCount.value = await reviewApi.getReviewCount(sourceTaskId.value)
      } catch {
        reportReviewCount.value = 0
      }
    } else {
      reportReviewCount.value = 0
    }

    // 2. 用例级复核历史（真实端点）
    caseReviewMap.value = {}
    if (sourceTaskId.value !== '') {
      try {
        const history = await reviewApi.getReviewHistory(sourceTaskId.value)
        const grouped: Record<string, ReviewHistoryItemDomain[]> = {}
        for (const item of history) {
          const tcId = item.testCaseId ? String(item.testCaseId) : ''
          if (!tcId) continue
          if (!grouped[tcId]) grouped[tcId] = []
          grouped[tcId].push(item)
        }
        const map: Record<string, CaseReviewState> = {}
        for (const [tcId, items] of Object.entries(grouped)) {
          // 计数 = 该用例已复核「结果」数（按 result_id 去重，非留痕行数；§4.1，P2-3）
          const distinctResults = new Set(items.map((i) => i.resultId).filter((id) => id != null))
          map[tcId] = {
            hasReview: items.length > 0,
            count: distinctResults.size,
            items: [...items].reverse(),
          }
        }
        caseReviewMap.value = map
      } catch (e: any) {
        const msg = toUserErrorMessage(e, '复核数据加载失败，请稍后重试')
        reviewsError.value = msg
        console.error('加载报告复核历史失败:', e)
      }
    }

    loadingReviews.value = false
  }

  /**
   * 双路径入口 A：跳来源任务复核。
   * 经 `GET /tasks/{task_id}/cases/{caseId}/results` 溯源该用例结果行
   * （result_id / reviewed / reviewHistory），打开 §3.2 复核弹窗预填，
   * 提交 `POST /tasks/results/review`（逐条留痕）后刷新。
   */
  async function openManualReview(caseItem: any) {
    if (sourceTaskId.value === '') {
      const msg = '报告缺少来源任务，无法在报告页发起人工复核'
      reviewsError.value = msg
      notification.error(msg)
      return
    }
    const caseId = caseItem?.id ?? caseItem?.testCaseId
    if (!caseId) return

    try {
      // 溯源来源任务该用例结果行（含 result_id / reviewed / reviewHistory）
      const resultsData = await tasksApi.getCaseResults(sourceTaskId.value, caseId)
      const resultRows = (resultsData?.results ?? []).filter((r: any) => r?.id != null)
      if (!resultRows.length) {
        const msg = '来源任务未查询到该用例结果行，无法复核'
        reviewsError.value = msg
        notification.error(msg)
        return
      }
      // 结果摘要行完整透传（对齐任务详情侧 TestExecutionComponent 契约）：
      // caseName=用例名，deviceName/apiName=设备/API 名，reviewed=已复核徽标
      const resultMetas = resultRows.map((r: any) => ({
        resultId: r.id,
        executionStatus: r.executionStatus,
        evaluationStatus: r.evaluationStatus,
        deviceName: r.deviceName,
        apiName: r.apiName,
        reviewed: r.reviewed,
      }))
      // 单条复核附带该结果复核历史（多次复核追加不覆盖）
      const reviewHistory = resultRows.length === 1
        ? (resultRows[0].reviewHistory ?? [])
        : []

      // 打开复核弹窗；用户点「取消」是正常操作（open() 取消即 reject），不落错误分支
      const res = await modalControl.open(MODAL_TYPES.RESULT_REVIEW, {
        title: '人工复核',
        taskId: sourceTaskId.value,
        caseName: caseItem?.name ?? resultsData?.caseName,
        results: resultMetas,
        reviewHistory,
      }).catch(() => undefined)
      if (res) {
        const payload: ReviewSubmitPayload = {
          resultIds: resultRows.map((r: any) => r.id),
          executionStatus: res.executionStatus,
          evaluationStatus: res.evaluationStatus,
          comment: res.comment,
        }
        await reviewApi.submitReview(payload)
        // 刷新来源任务复核历史与报告级计数
        const report = reportDataRef()
        if (report) await loadReportReviews(report)
      }
    } catch (e: any) {
      console.error('人工复核失败:', e)
      const msg = toUserErrorMessage(e, '人工复核提交失败，请稍后重试')
      reviewsError.value = msg
      notification.error(msg, toUserErrorDetail(e))
    }
  }

  /** 打开复核明细弹窗（用例卡片「人工复核」Badge 点击） */
  function openReviewDetail(caseItem: any) {
    const caseId = caseItem?.id ?? caseItem?.testCaseId
    const state = getCaseReview(caseId)
    if (!state.hasReview) return
    return state
  }

  // ===== AI 复核（§4.3 状态机；真实端点 INT-800/INT-1068/INT-1070） =====

  /** 清理该用例轮询定时器（落位/超时/重置时调用） */
  function clearAiPoll(caseId: string): void {
    const timer = aiPollTimers.get(caseId)
    if (timer) {
      clearTimeout(timer)
      aiPollTimers.delete(caseId)
    }
  }

  /**
   * 轮询该用例首个结果的 AI 复核历史至落位（§5.6）。
   * `GET /tasks/results/{task_id}/ai-review-history`（Query result_id，每 3s）；
   * completed/failed 即推进弹窗到结论阶段；超时保留 running 态并给出可关闭的错误提示。
   */
  function pollAiReviewUntilSettled(caseId: string, taskId: string | number, resultId: number | string, attempt = 0): void {
    if (attempt >= AI_REVIEW_POLL_MAX_ATTEMPTS) {
      clearAiPoll(caseId)
      // 超时：置 completed 并给错误（弹窗显错误行且可关闭，不卡「复核中」）
      const run = aiReviewMap.value[caseId]
      if (run && run.phase === 'running') {
        aiReviewMap.value[caseId] = { phase: 'completed', record: run.record, error: 'AI 复核超时未出结论，请稍后重试' }
      }
      return
    }
    const timer = setTimeout(async () => {
      try {
        const history = await reviewApi.getAiReviewHistory(taskId, { resultId })
        const settled = history.find(
          (r) => r.resultId === Number(resultId) && (r.status === 'completed' || r.status === 'failed'),
        )
        if (settled) {
          clearAiPoll(caseId)
          aiReviewMap.value[caseId] = { phase: 'completed', record: settled, error: '' }
          return
        }
        pollAiReviewUntilSettled(caseId, taskId, resultId, attempt + 1)
      } catch {
        pollAiReviewUntilSettled(caseId, taskId, resultId, attempt + 1)
      }
    }, AI_REVIEW_POLL_INTERVAL_MS)
    aiPollTimers.set(caseId, timer)
  }

  /**
   * 发起 AI 复核：待发起 → 执行中 → 已完成。
   * `POST /tasks/results/ai-review`（真实端点，幂等：同结果同维度已有时后端复用最近结论）；
   * 后端异步复检（status=running/pending）时按 §5.6 轮询历史直至 completed/failed，弹窗状态行自动推进。
   */
  async function initiateAiReview(caseItem: any) {
    const caseId = String(caseItem?.id ?? caseItem?.testCaseId ?? '')
    if (!caseId) return
    if (getAiRun(caseId).phase === 'running') return

    aiReviewMap.value[caseId] = { phase: 'running', record: null, error: '' }
    try {
      // 溯源来源任务该用例结果行 → 取首个结果发起
      let resultIds: (string | number)[] = []
      if (sourceTaskId.value !== '') {
        const resultsData = await tasksApi.getCaseResults(sourceTaskId.value, caseId)
        resultIds = (resultsData?.results ?? []).map((r: any) => r?.id).filter((id: any) => id != null)
      }
      if (!resultIds.length) {
        aiReviewMap.value[caseId] = { phase: 'completed', record: null, error: '该用例无可发起 AI 复核的结果' }
        return
      }
      const record = await reviewApi.submitAiReview({ resultIds })
      // 同步已落位（completed/failed）直接进结论阶段；否则异步复检 → 轮询推进（§5.6）
      if (record.status === 'completed' || record.status === 'failed') {
        aiReviewMap.value[caseId] = { phase: 'completed', record, error: '' }
      } else {
        aiReviewMap.value[caseId] = { phase: 'running', record, error: '' }
        pollAiReviewUntilSettled(caseId, sourceTaskId.value, record.resultId || Number(resultIds[0]))
      }
    } catch (e: any) {
      clearAiPoll(caseId)
      aiReviewMap.value[caseId] = { phase: 'completed', record: null, error: e?.message || 'AI 复核失败' }
    }
  }

  /** 采纳 AI 复核结论 → 落人工复核语义（打开 §3.2 复核弹窗预填 AI 判定；确认后单次 adopt，防双写留痕） */
  async function adoptAiReview(caseItem: any) {
    const caseId = String(caseItem?.id ?? caseItem?.testCaseId ?? '')
    const run = getAiRun(caseId)
    if (!run.record) return
    const record = run.record
    const resultId = record.resultId

    // AI 判定 → 评估状态预填（对齐 React aiVerdictToEvaluationStatus：通过→已完成；不通过→评估失败；存疑→不预填）
    const suggestedEvaluation = record.verdict === 'passed'
      ? 'completed'
      : record.verdict === 'failed'
        ? 'failed'
        : undefined
    try {
      // 溯源该结果行补设备/API 名与当前执行状态（摘要行展示，与人工复核入口同源；取数失败不阻断弹窗）
      const resultsData = sourceTaskId.value !== ''
        ? await tasksApi.getCaseResults(sourceTaskId.value, caseId).catch(() => null)
        : null
      const row = resultsData?.results?.find((r: any) => String(r.id) === String(resultId))
      // 打开复核弹窗预填 AI 判定的评估状态 + 备注（AI 理由），用户确认即可提交；
      // 点「取消」是正常操作（open() 取消即 reject），不落错误分支
      const res = await modalControl.open(MODAL_TYPES.RESULT_REVIEW, {
        title: '人工复核',
        taskId: sourceTaskId.value,
        caseName: caseItem?.name ?? resultsData?.caseName,
        results: [{
          resultId,
          executionStatus: row?.executionStatus,
          evaluationStatus: suggestedEvaluation,
          deviceName: row?.deviceName,
          apiName: row?.apiName,
        }],
        reviewHistory: [],
        preset: { evaluationStatus: suggestedEvaluation, comment: record.reasoning },
      }).catch(() => undefined)
      if (res) {
        // 单次 adopt：POST /ai-review/{id}/adopt 内部复用 apply_review 落 test_result_reviews + 统计重算，
        // 前端不补调 /tasks/results/review（防双写留痕）
        await reviewApi.adoptAiReview(record.id, {
          executionStatus: res.executionStatus,
          evaluationStatus: res.evaluationStatus || suggestedEvaluation,
          comment: res.comment || record.reasoning,
        })
        aiReviewMap.value[caseId] = { ...run, phase: 'adopted' }
        const report = reportDataRef()
        if (report) await loadReportReviews(report)
      }
    } catch (e: any) {
      console.error('采纳 AI 复核失败:', e)
      const msg = toUserErrorMessage(e, '采纳 AI 复核失败，请稍后重试')
      reviewsError.value = msg
      notification.error(msg, toUserErrorDetail(e))
    }
  }

  /** 驳回 AI 复核结论：保留原判定，AI 记录标记已驳回（POST /ai-review/{id}/reject，真实端点） */
  async function rejectAiReview(caseItem: any) {
    const caseId = String(caseItem?.id ?? caseItem?.testCaseId ?? '')
    const run = getAiRun(caseId)
    if (!run.record) return
    try {
      await reviewApi.rejectAiReview(run.record.id)
      aiReviewMap.value[caseId] = { ...run, phase: 'rejected' }
    } catch (e: any) {
      console.error('驳回 AI 复核失败:', e)
      const msg = toUserErrorMessage(e, '驳回 AI 复核失败，请稍后重试')
      reviewsError.value = msg
      notification.error(msg, toUserErrorDetail(e))
    }
  }

  /** 忽略（待查）：关闭暂不处理，AI 结论保留待查 */
  function ignoreAiReview(caseItem: any) {
    const caseId = String(caseItem?.id ?? caseItem?.testCaseId ?? '')
    const run = getAiRun(caseId)
    if (run.phase === 'running') return
    aiReviewMap.value[caseId] = { ...run, phase: 'ignored' }
  }

  /** 重置状态（组件卸载） */
  function resetReportReviews() {
    // 清理 AI 复核轮询定时器（§5.6：卸载/重置不残留后台轮询）
    aiPollTimers.forEach((timer) => clearTimeout(timer))
    aiPollTimers.clear()
    reportReviewCount.value = 0
    caseReviewMap.value = {}
    aiReviewMap.value = {}
    sourceTaskId.value = ''
    reviewsError.value = ''
  }

  onUnmounted(() => {
    resetReportReviews()
  })

  return {
    reportReviewCount,
    totalReviewCount,
    caseReviewMap,
    caseIdsWithReview,
    aiReviewMap,
    sourceTaskId,
    loadingReviews,
    reviewsError,
    loadReportReviews,
    getCaseReview,
    openManualReview,
    openReviewDetail,
    initiateAiReview,
    adoptAiReview,
    rejectAiReview,
    ignoreAiReview,
    resetReportReviews,
  }
}
