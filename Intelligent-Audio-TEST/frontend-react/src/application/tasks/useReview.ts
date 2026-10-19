/**
 * 复核 application 层（19 规范 §3.6 落位；CQRS：命令侧 submitReview mutation，
 * 查询侧 reviewCount / reviewHistory query）。
 * 共享 infrastructure（domain/dto/adapter/api/review*）由报告侧 INT-793 卡与任务侧
 * INT-795 卡共同落位，本层只消费共享 API 出口（submitReview / fetchReviewCount /
 * fetchReviewHistory），不重写 infra。
 * 提交成功后 invalidate 任务详情 + 复核计数/历史，统计按复核后判定重算。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  ReviewHistoryItem,
  ReviewSubmitPayload,
  ReviewSubmitResult,
} from '@/domain/models/review'
import {
  fetchReviewCount,
  fetchReviewHistory,
  submitReview,
} from '@/infrastructure/api/reviewApi'

export const REVIEW_QUERY_KEY = ['tasks', 'review'] as const

/** 提交人工复核（mutation；成功后刷新任务详情与复核计数） */
export function useSubmitReview() {
  const queryClient = useQueryClient()
  return useMutation<ReviewSubmitResult, Error, ReviewSubmitPayload>({
    mutationFn: (payload) => submitReview(payload),
    onSuccess: (_data, payload) => {
      queryClient.invalidateQueries({ queryKey: ['tasks', 'detail'] })
      queryClient.invalidateQueries({ queryKey: REVIEW_QUERY_KEY })
      // 复核改判会影响任务统计徽章行/图表；列表页同步失效（按复核后判定重算）
      if (payload.resultIds.length > 0) {
        queryClient.invalidateQueries({ queryKey: ['tasks', 'list'] })
      }
    },
  })
}

/** 任务复核计数（任务头/统计徽章；与任务详情 review_count 同源，页面可二选一） */
export function useReviewCount(taskId: number) {
  return useQuery({
    queryKey: [...REVIEW_QUERY_KEY, 'count', taskId],
    queryFn: () => fetchReviewCount(taskId),
    staleTime: 30_000,
  })
}

/** 任务复核历史（历史抽屉数据源） */
export function useReviewHistory(taskId: number) {
  return useQuery<ReviewHistoryItem[]>({
    queryKey: [...REVIEW_QUERY_KEY, 'history', taskId],
    queryFn: () => fetchReviewHistory(taskId),
    staleTime: 30_000,
  })
}
