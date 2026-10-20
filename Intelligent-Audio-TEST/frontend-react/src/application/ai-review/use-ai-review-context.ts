/**
 * 复核上下文装配 hook（application/ai-review，19 规范 §5.3，INT-1064）。
 * 打开复核会话时聚合现有端点构造 AiReviewContext（无新后端，08 §3.8「可先行」）：
 *   GET /tasks/{id}/cases/{id}/results   → 设备×结果列表（result_id/复核标注/评语）
 *   GET /tasks/{id}/cases/{id}/detail    → 设备×维度表（低分维度识别，默认复核维度）
 *   GET /tasks/results/{task_id}/ai-review-history → 已有 ai_reviews 结论（按 testCaseId 过滤，幂等复用）
 * 装配结果作为灵犀Agent 复核会话系统提示 + 首条 assistant 摘要卡输入（§5.2/§5.3）。
 */
import { useQuery } from '@tanstack/react-query'

import type { AiReviewContext } from '@/domain/models/review'
import { fetchAiReviewHistory, fetchCaseResults } from '@/infrastructure/api/reviewApi'
import { fetchCaseExecutionDetail } from '@/infrastructure/api/test-execution-api'
import type { CaseMetricPoint } from '@/domain/models/testExecution'

/** 维度 key（@round:{n}/@overall 后缀剥离）→ 维度名 */
function stripRoundSuffix(key: string): string {
  return key.replace(/@(round:\d+|overall)$/i, '')
}

/** 设备×维度表 → 维度名 → 聚合分（多设备/多轮平均；非数值维度跳过，null 无数值） */
function aggregateDimensionScores(
  devices: Array<{ metrics: CaseMetricPoint[] }>
): Array<{ name: string; score: number | null }> {
  const dimMap: Record<string, { sum: number; count: number }> = {}
  for (const device of devices) {
    for (const metric of device.metrics ?? []) {
      const name = stripRoundSuffix(metric.dimension)
      if (!name) continue
      // 维度值为字符串（CaseMetricPoint.value: string）；可解析为数值才参与聚合
      const parsed = Number(metric.value)
      if (!Number.isFinite(parsed)) continue
      dimMap[name] ??= { sum: 0, count: 0 }
      dimMap[name].sum += parsed
      dimMap[name].count += 1
    }
  }
  return Object.entries(dimMap)
    .map(([name, { sum, count }]) => ({
      name,
      score: count > 0 ? sum / count : null,
    }))
    .sort((a, b) => (a.score ?? Infinity) - (b.score ?? Infinity))
}

/**
 * 复核上下文装配（enabled=false 时惰性不请求；消费侧 = 复核会话 Dialog 打开时）。
 * 返回 { context, isLoading, isError, refetch }。
 */
export function useAiReviewContext(
  taskId: number,
  caseId: string,
  enabled: boolean
) {
  const resultsQuery = useQuery({
    queryKey: ['tasks', 'cases', taskId, caseId, 'results'],
    queryFn: () => fetchCaseResults(taskId, caseId),
    enabled,
    staleTime: 15_000,
  })
  const detailQuery = useQuery({
    queryKey: ['test-execution', 'case-detail', taskId, caseId],
    queryFn: () => fetchCaseExecutionDetail(taskId, caseId),
    enabled,
    staleTime: 30_000,
  })
  const historyQuery = useQuery({
    queryKey: ['tasks', 'ai-reviews', 'history', taskId],
    queryFn: () => fetchAiReviewHistory(taskId),
    enabled: enabled && Boolean(taskId),
    staleTime: 15_000,
  })

  const results = resultsQuery.data
  const detail = detailQuery.data
  const history = historyQuery.data ?? []

  // 无执行结果的用例不开放复核（§5.2 可发起对象：评估已完成/失败且存在执行结果）
  const hasResults = (results?.results.length ?? 0) > 0

  const context: AiReviewContext | null =
    results && detail && enabled
      ? {
          taskId,
          caseId,
          caseName: results.caseName || detail.name || '用例',
          evaluationStatus: detail.evaluationStatus ?? null,
          deviceResults: results.results,
          dimensionScores: aggregateDimensionScores(detail.devices),
          // 现有复核/评语（results 行 lastReviewComment 首条非空）
          reasoning:
            results.results.find((r) => r.lastReviewComment)?.lastReviewComment ??
            null,
          // 已有 ai_reviews 结论（按 testCaseId 过滤，幂等复用；任务历史可能含其他用例记录）
          existingReviews: history.filter((r) => r.testCaseId === caseId),
        }
      : null

  return {
    context,
    hasResults,
    isLoading:
      resultsQuery.isLoading || detailQuery.isLoading || historyQuery.isLoading,
    isError: resultsQuery.isError || detailQuery.isError || historyQuery.isError,
    refetch: () => {
      void resultsQuery.refetch()
      void detailQuery.refetch()
      void historyQuery.refetch()
    },
  }
}
