/**
 * 任务侧 AI 复核状态机 hook（application/ai-review，19 规范 §5.5/§5.9，INT-1064）。
 * 待发起→执行中→已完成→已采纳/已驳回/待查（§2.1）；真实端点（INT-800 done）：
 *   保存复核结论 → POST /tasks/results/ai-review（异步复检 → ai_reviews completed/failed）
 *   采纳         → POST /tasks/results/ai-review/{id}/adopt（单次调用，落人工复核语义；
 *                  **前端不补调 /tasks/results/review，会双写留痕**——审核注记 1）
 *   驳回         → POST /tasks/results/ai-review/{id}/reject（标记已驳回备查，原判定不变）
 * 异步执行（ai_reviews.status=pending/running）由轮询历史推进（completed/failed 收敛）。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import type {
  AiReviewAdoptPayload,
  AiReviewRecord,
  AiReviewRequest,
  AiReviewVerdict,
} from '@/domain/models/review'
import {
  adoptAiReview,
  fetchAiReviewHistory,
  rejectAiReview,
  requestAiReview,
} from '@/infrastructure/api/reviewApi'

export type AiReviewPhase =
  | 'idle' // 待发起
  | 'running' // 执行中（保存结论已提交，后端异步复检）
  | 'completed' // 已完成（结论落位）
  | 'adopted' // 已采纳（落人工复核语义）
  | 'rejected' // 已驳回
  | 'ignored' // 待查（忽略）

/** AI 结论 → 人工复核预填评估状态（§2.1：复核通过→已完成；不通过→评估失败；存疑→不预填） */
export function aiVerdictToEvaluationStatus(
  verdict: AiReviewVerdict | undefined
): 'completed' | 'failed' | undefined {
  if (verdict === 'passed') return 'completed'
  if (verdict === 'failed') return 'failed'
  return undefined
}

/** 任务侧 AI 复核状态机（独立于报告侧 useReportReviews；报告侧归 INT-1065 收敛共用） */
export function useAiReview(taskId: number, caseId: string) {
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<AiReviewPhase>('idle')
  const [record, setRecord] = useState<AiReviewRecord>()
  /** 本次发起的记录 id（执行中按它从历史定位推进状态） */
  const [recordId, setRecordId] = useState<number>()
  /** INT-1545：记录归属任务 id（发起响应 item.task_id）。容器任务下页面 taskId 是合并
   * 任务、结果归属源任务，后端 ai_reviews 写在源任务下——轮询历史须按归属任务查 */
  const [recordTaskId, setRecordTaskId] = useState<number>()
  const [error, setError] = useState<string>()

  const historyTaskId = recordTaskId ?? taskId

  const historyQuery = useQuery({
    queryKey: ['tasks', 'ai-reviews', 'history', historyTaskId],
    queryFn: () => fetchAiReviewHistory(historyTaskId),
    enabled: Boolean(historyTaskId),
    // 执行中由真实后端异步驱动（pending/running → completed/failed）：每 3s 轮询历史推进
    refetchInterval: phase === 'running' ? 3000 : false,
  })

  // 按真实后端 status 推进（§5.7 注记 2：未知 status 容错——仅 completed/failed 收敛，其余保持执行中）
  useEffect(() => {
    if (!recordId) return
    const current = historyQuery.data?.find((r) => r.id === recordId)
    if (!current) return
    if (current.status === 'completed') {
      setRecord(current)
      setPhase('completed')
      setRecordId(undefined)
    } else if (current.status === 'failed' || current.status === 'canceled') {
      setError(
        current.status === 'failed'
          ? 'AI 复核执行失败，请稍后重试'
          : 'AI 复核已取消'
      )
      setPhase('idle')
      setRecordId(undefined)
    }
    // pending/running/未知值：保持执行中，下次轮询继续
  }, [historyQuery.data, recordId])

  /** 保存复核结论（POST /tasks/results/ai-review；异步复检 → 轮询推进 completed） */
  const save = async (payload: AiReviewRequest) => {
    setPhase('running')
    setError(undefined)
    try {
      const result = await requestAiReview(taskId, caseId, payload)
      setRecord(result)
      // 记录归属任务：发起响应 item.task_id（容器任务下 = 结果所属源任务）
      setRecordTaskId(result.taskId || taskId)
      if (result.status === 'completed') {
        setPhase('completed')
        setRecordId(undefined)
      } else if (result.status === 'failed' || result.status === 'canceled') {
        setError(
          result.status === 'failed'
            ? 'AI 复核执行失败，请稍后重试'
            : 'AI 复核已取消'
        )
        setPhase('idle')
        setRecordId(undefined)
      } else {
        // pending/running：异步执行中，refetchInterval 驱动轮询历史推进
        setRecordId(result.id)
      }
      void queryClient.invalidateQueries({
        queryKey: ['tasks', 'ai-reviews', 'history', historyTaskId],
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核发起失败')
      setPhase('idle')
    }
  }

  /** 采纳：单次调 POST /ai-review/{id}/adopt 落人工复核语义（不补调 /tasks/results/review，避免双写留痕——审核注记 1） */
  const adopt = async (payload?: AiReviewAdoptPayload): Promise<boolean> => {
    if (!record) return false
    // 存疑无明确判定可采纳（§5.5「uncertain→不预填留人工」）：入口已隐藏，兜底避免空改判载荷触发后端 400
    if (record.verdict === 'uncertain') return false
    try {
      const updated = await adoptAiReview(record.id, {
        evaluationStatus:
          payload?.evaluationStatus ??
          aiVerdictToEvaluationStatus(record.verdict),
        comment: payload?.comment ?? record.reasoning,
      })
      setRecord(updated)
      setPhase('adopted')
      void queryClient.invalidateQueries({
        queryKey: ['tasks', 'ai-reviews', 'history', historyTaskId],
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
    try {
      const updated = await rejectAiReview(record.id)
      setRecord(updated)
      setPhase('rejected')
      void queryClient.invalidateQueries({
        queryKey: ['tasks', 'ai-reviews', 'history', historyTaskId],
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核驳回失败')
    }
  }

  /** 忽略（关闭暂不处理）：AI 结论保留待查 */
  const ignore = () => {
    setPhase('ignored')
  }

  const reset = () => {
    setPhase('idle')
    setRecord(undefined)
    setRecordId(undefined)
    setRecordTaskId(undefined)
    setError(undefined)
  }

  return {
    phase,
    record,
    error,
    history: historyQuery.data ?? [],
    historyLoading: historyQuery.isLoading,
    save,
    adopt,
    reject,
    ignore,
    reset,
  }
}
