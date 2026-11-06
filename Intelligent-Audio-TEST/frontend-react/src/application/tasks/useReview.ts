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
import { fetchContainerSourceTrace } from '@/infrastructure/api/cherry-pick-api'
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

/** 任务复核历史（历史抽屉数据源；enabled=false 时不查询——抽屉未开或 taskId<=0 时避免无效请求） */
export function useReviewHistory(taskId: number, enabled: boolean) {
  return useQuery<ReviewHistoryItem[]>({
    queryKey: [...REVIEW_QUERY_KEY, 'history', taskId],
    queryFn: () => fetchReviewHistory(taskId),
    enabled,
    staleTime: 30_000,
  })
}

/**
 * 复核记录归属范围（INT-1626）。
 * 挑选合并容器（cherry-pick）不拥有 test_results：容器行引用源任务的结果行，
 * 复核留痕写侧按 `test_results.task_id`（源任务）落库，读侧若仍按容器 id 查则恒空。
 * 普通任务归属=自身，行为与改动前一致。
 */
export interface ReviewRecordScope {
  /** 复核留痕归属任务 id 集合（普通任务=页面任务；容器=来源任务集合） */
  taskIds: number[]
  /** 容器引用的结果 id（把来源任务历史裁剪到容器范围；普通任务 null=不裁剪） */
  resultIds: number[] | null
}

/** 复核范围查询键（挂在 REVIEW_QUERY_KEY 下，提交后统一失效） */
export const REVIEW_SCOPE_QUERY_KEY = [...REVIEW_QUERY_KEY, 'scope'] as const

/**
 * 复核范围解析：探测页面任务是否为挑选合并容器（GET /tasks/cherry-picks/{id}/source）。
 * 非容器/溯源失败 → 回落 { taskIds: [taskId], resultIds: null }，绝不阻断任务详情；
 * 溯源未返回前 scope=null（消费侧按加载态处理，避免先按容器 id 查出空态闪一下）。
 */
export function useReviewRecordScope(taskId: number) {
  const query = useQuery({
    queryKey: [...REVIEW_SCOPE_QUERY_KEY, taskId],
    queryFn: () => fetchContainerSourceTrace(taskId),
    enabled: taskId > 0,
    staleTime: 60_000,
  })

  const groups = query.data?.groups ?? []
  let scope: ReviewRecordScope | null = null
  if (taskId > 0) {
    if (groups.length > 0) {
      const taskIds = [...new Set(groups.map((g) => g.source_task_id))]
      const resultIds = groups.flatMap((g) =>
        (g.results ?? []).map((r) => r.result_id)
      )
      scope = { taskIds, resultIds }
    } else if (query.isSuccess || query.isError) {
      scope = { taskIds: [taskId], resultIds: null }
    }
  }

  return {
    scope,
    /** 是否为挑选合并容器（有溯源引用即容器） */
    isContainer: scope?.resultIds != null,
    isLoading: taskId > 0 && query.isLoading,
    isError: query.isError,
  }
}

/**
 * 复核历史（容器任务按来源任务聚合，且仅保留容器引用结果的留痕）。
 * 普通任务与 useReviewHistory 等价；容器任务并行查各来源任务后按 resultIds 裁剪。
 */
export function useScopedReviewHistory(taskId: number, enabled: boolean) {
  const { scope, isLoading: scopeLoading } = useReviewRecordScope(taskId)
  const taskIds = scope?.taskIds ?? []
  const resultIds = scope?.resultIds ?? null

  const query = useQuery<ReviewHistoryItem[]>({
    queryKey: [
      ...REVIEW_QUERY_KEY,
      'history-scope',
      taskId,
      taskIds.join(','),
      resultIds ? `results:${resultIds.length}` : 'all',
    ],
    queryFn: async () => {
      const lists = await Promise.all(taskIds.map((id) => fetchReviewHistory(id)))
      const items = lists.flat()
      if (!resultIds) return items
      const picked = new Set(resultIds)
      return items.filter((item) => picked.has(item.resultId))
    },
    enabled: enabled && taskIds.length > 0,
    staleTime: 30_000,
  })

  return {
    ...query,
    scope,
    /** 来源任务历史按结果去重后的已复核条数（「已复核 n 条」口径同后端 count_reviewed_results） */
    reviewedResultCount: new Set((query.data ?? []).map((item) => item.resultId))
      .size,
    isLoading: scopeLoading || query.isLoading,
  }
}
