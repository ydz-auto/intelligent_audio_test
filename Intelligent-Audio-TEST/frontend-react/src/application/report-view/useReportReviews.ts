/**
 * 报告侧人工复核 + AI 复核 hooks（application/report-view，19 规范 §4.4，INT-793）。
 * - useReportReviews：源任务复核数据（review_count 统计徽章 + 用例 reviewed 标记 map +
 *   复核历史 + 提交 mutation）
 * - useCaseResults：复核弹窗数据源（GET /tasks/{id}/cases/{caseId}/results → result_id/复核标注）
 * AI 复核状态机已收敛共用件 application/ai-review/use-ai-review（INT-1065 报告侧共用，不留双口径）。
 *
 * 报告为落库快照；复核操作按 §4.2 路径 A 跳来源任务结果（task_id + result_id 溯源），
 * 提交后 invalidate 源任务详情（review_count / reviewed 标记），报告重新生成后快照刷新。
 * AI 复核异步执行（后端 ai_reviews.status=pending/running → completed/failed）由轮询历史推进（INT-1063 去桩）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { ReviewSubmitPayload } from '@/domain/models/review'
import type { ReportDetailData } from '@/domain/models/report'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
import {
  fetchCaseResults,
  fetchReviewHistory,
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
