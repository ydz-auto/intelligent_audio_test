/**
 * 报告侧人工复核 + AI 复核 hooks（application/report-view，19 规范 §4.4，INT-793）。
 * - useReportReviews：源任务复核数据（review_count 统计徽章 + 用例 reviewed 标记 map +
 *   复核历史 + 提交 mutation）
 * - useCaseResults：复核弹窗数据源（GET /tasks/{id}/cases/{caseId}/results → result_id/复核标注）
 * - useAiReview：AI 复核状态机（待发起→执行中→已完成→已采纳/已驳回/待查；§2.1）
 *
 * 报告为落库快照；复核操作按 §4.2 路径 A 跳来源任务结果（task_id + result_id 溯源），
 * 提交后 invalidate 源任务详情（review_count / reviewed 标记），报告重新生成后快照刷新。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import type {
  AiReviewRecord,
  AiReviewRequest,
  AiReviewVerdict,
  ReviewSubmitPayload,
} from '@/domain/models/review'
import type { ReportDetailData } from '@/domain/models/report'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
import {
  adoptAiReview,
  fetchAiReviewHistory,
  fetchCaseResults,
  fetchReviewHistory,
  rejectAiReview,
  requestAiReview,
  submitReview,
} from '@/infrastructure/api/reviewApi'

/** 报告源任务复核数据（仅任务型报告；task_id 缺失/对比报告不启用） */
export function useReportReviews(report?: ReportDetailData) {
  const taskId = report?.task_id
  const enabled = Boolean(taskId) && report?.type === 'task'
  const queryClient = useQueryClient()

  const taskQuery = useQuery({
    queryKey: ['tasks', 'detail', taskId],
    queryFn: () => fetchTaskDetail(taskId as number),
    enabled,
    staleTime: 30_000,
  })

  /** 用例 case_id → 是否已复核（TaskCaseBrief.reviewed 驱动「人工复核」Badge） */
  const reviewedCases = useMemo(() => {
    const map: Record<string, boolean> = {}
    for (const c of taskQuery.data?.cases ?? []) {
      map[c.case_id] = c.reviewed === true
    }
    return map
  }, [taskQuery.data])

  /** 报告头「已复核 {n} 条」统计徽章数据源（源任务 review_count，INT-734 实测回填） */
  const reviewCount = taskQuery.data?.review_count ?? 0

  /** 复核历史（任务级；报告卡片明细按用例从 useCaseResults.reviewHistory 聚合） */
  const historyQuery = useQuery({
    queryKey: ['tasks', 'reviews', 'history', taskId],
    queryFn: () => fetchReviewHistory(taskId as number),
    enabled,
    staleTime: 15_000,
  })

  const submitMutation = useMutation({
    mutationFn: (payload: ReviewSubmitPayload) => submitReview(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks', 'detail', taskId] })
      void queryClient.invalidateQueries({ queryKey: ['tasks', 'reviews', 'history', taskId] })
    },
  })

  const refetchTask = () => taskQuery.refetch()

  return {
    taskId,
    taskLoading: taskQuery.isLoading,
    taskStatus: taskQuery.data?.status,
    /** 任务用例简报（AI 结论卡「原评估判定」/复核弹窗状态摘要数据源） */
    taskCases: taskQuery.data?.cases ?? [],
    reviewCount,
    reviewedCases,
    reviewHistory: historyQuery.data ?? [],
    historyLoading: historyQuery.isLoading,
    submit: submitMutation.mutateAsync,
    submitting: submitMutation.isPending,
    refetchTask,
  }
}

/** 用例执行结果（复核弹窗数据源；enabled=false 时惰性不请求） */
export function useCaseResults(taskId: number, caseId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['tasks', 'cases', taskId, caseId, 'results'],
    queryFn: () => fetchCaseResults(taskId, caseId),
    enabled,
    staleTime: 15_000,
  })
}

/** 用例 AI 复核状态机（§2.1：待发起→执行中→已完成→已采纳/已驳回/待查；端点留桩 `// 待接线`） */
export function useAiReview(taskId: number, caseId: string) {
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<
    'idle' | 'running' | 'completed' | 'adopted' | 'rejected' | 'ignored'
  >('idle')
  const [record, setRecord] = useState<AiReviewRecord>()
  const [error, setError] = useState<string>()

  const historyQuery = useQuery({
    queryKey: ['tasks', 'ai-reviews', 'history', taskId],
    queryFn: () => fetchAiReviewHistory(taskId),
    enabled: Boolean(taskId),
  })

  /** 发起：提交 → 异步执行（模拟轮询，端点留桩） → 结论落位 */
  const initiate = async (payload: AiReviewRequest) => {
    setPhase('running')
    setError(undefined)
    try {
      // 待接线：真实端点异步执行中由后端驱动进度；桩实现模拟延迟后返回结论
      await new Promise((resolve) => setTimeout(resolve, 1600))
      const result = await requestAiReview(taskId, caseId, payload)
      setRecord(result)
      setPhase('completed')
      void queryClient.invalidateQueries({
        queryKey: ['tasks', 'ai-reviews', 'history', taskId],
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核失败')
      setPhase('idle')
    }
  }

  /** 采纳：AI 结论转人工复核语义（打开复核弹窗预填由消费侧处理；记录标已采纳） */
  const adopt = async (): Promise<boolean> => {
    if (!record) return false
    try {
      const updated = await adoptAiReview(record.id, {
        evaluationStatus: aiVerdictToEvaluationStatus(record.verdict),
        comment: record.reasoning,
      })
      setRecord(updated)
      setPhase('adopted')
      void queryClient.invalidateQueries({
        queryKey: ['tasks', 'ai-reviews', 'history', taskId],
      })
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核采纳失败')
      return false
    }
  }

  /** 驳回：保留原判定，AI 记录标记已驳回备查 */
  const reject = async () => {
    if (!record) return
    const updated = await rejectAiReview(record.id)
    setRecord(updated)
    setPhase('rejected')
    void queryClient.invalidateQueries({
      queryKey: ['tasks', 'ai-reviews', 'history', taskId],
    })
  }

  /** 忽略（关闭暂不处理）：AI 结论保留待查 */
  const ignore = () => {
    setPhase('ignored')
  }

  return {
    phase,
    record,
    error,
    history: historyQuery.data ?? [],
    historyLoading: historyQuery.isLoading,
    initiate,
    adopt,
    reject,
    ignore,
    reset: () => {
      setPhase('idle')
      setRecord(undefined)
      setError(undefined)
    },
  }
}

/** AI 结论 → 人工复核预填评估状态（§2.1：复核通过→已完成；复核不通过→评估失败；存疑→不预填） */
export function aiVerdictToEvaluationStatus(
  verdict: AiReviewVerdict | undefined
): 'completed' | 'failed' | undefined {
  if (verdict === 'passed') return 'completed'
  if (verdict === 'failed') return 'failed'
  return undefined
}
