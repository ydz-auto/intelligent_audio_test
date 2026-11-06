/**
 * 报告对比/二次对比（application 层，INT-434 P2-20 收敛）。
 * 基于任务（compareReports）与基于已选报告（secondaryCompareReports）双通道，
 * 页面与 Dialog 不直 import infrastructure API。
 * §4.6 对比配置（对比维度/指标/方式）随批透传，mock 不消费留待接线。
 * INT-935 契约修正：secondary-compare 后端为异步生成（立即返回 { reportKey, status }，
 * 真实 report_id 经 SSE secondary_compare_generated 事件回传），本层提供
 * waitForReportGenerated 统一等待（generate-task/regenerate 走 report_generated，按 taskId 匹配）。
 */
import { useCallback } from 'react'
import { toast } from 'sonner'

import type { ReportCompareConfig } from '@/domain/models/report'
import {
  compareReports,
  secondaryCompareReports,
  type SecondaryCompareResult,
} from '@/infrastructure/api/reports-api'
import {
  subscribeSse,
  SSE_EVENT_CHANNELS,
} from '@/infrastructure/realtime/sse'

/** 异步生成等待键：taskId（generate-task/regenerate）或 reportKey（secondary-compare） */
export interface ReportGeneratedWaitKey {
  taskId?: number
  reportKey?: number[]
}

/**
 * 等待报告生成完成（异步生成链路事件契约）：
 * - taskId → 订阅 report_generated，匹配 data.taskId === taskId
 * - reportKey → 订阅 secondary_compare_generated，匹配 data.reportIds 升序 === reportKey 升序
 * 成功 resolve 真实 reportId；失败（success=false）/超时 reject。
 * 超时 180s 对齐 V9.7.10 Vue historyReports.ts handleBatchCompare；signal.abort 立即取消
 * （进度弹窗关闭时解绑，避免 SSE 连接泄漏）。
 * onOpen：SSE 订阅连接建立（status=open）后回调——调用方在 onOpen 前不提交 POST，
 * 杜绝 <1s 快速失败/完成时事件早于订阅连接到达的竞态。
 */
export function waitForReportGenerated(
  key: ReportGeneratedWaitKey,
  options: { timeoutMs?: number; signal?: AbortSignal; onOpen?: () => void } = {}
): Promise<number> {
  const { timeoutMs = 180_000, signal, onOpen } = options
  const isTaskKey = typeof key.taskId === 'number' && key.taskId > 0
  const reportKeyStr = (key.reportKey ?? [])
    .map(Number)
    .sort((a, b) => a - b)
    .join(',')

  return new Promise((resolve, reject) => {
    let settled = false
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    let unsubscribe: (() => void) | undefined

    function cleanup(): void {
      if (timeoutId) clearTimeout(timeoutId)
      if (signal) signal.removeEventListener('abort', onAbort)
      unsubscribe?.()
    }

    function fail(message: string): void {
      if (settled) return
      settled = true
      cleanup()
      reject(new Error(message))
    }

    function succeed(reportId: number): void {
      if (settled) return
      settled = true
      cleanup()
      resolve(reportId)
    }

    function onAbort(): void {
      fail('报告生成等待已取消')
    }

    if (signal) {
      if (signal.aborted) {
        fail('报告生成等待已取消')
        return
      }
      signal.addEventListener('abort', onAbort, { once: true })
    }

    timeoutId = setTimeout(() => fail('报告生成超时，请稍后重试'), timeoutMs)

    unsubscribe = subscribeSse({
      channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS],
      onStatusChange: (status) => {
        if (status === 'open') onOpen?.()
      },
      onEvent: (event) => {
        const data = (event.data ?? {}) as {
          taskId?: number
          reportIds?: number[]
          reportId?: number
          success?: boolean
          error?: string
        }
        if (isTaskKey) {
          if (event.eventType !== 'report_generated') return
          if (Number(data.taskId) !== Number(key.taskId)) return
        } else {
          if (event.eventType !== 'secondary_compare_generated') return
          const ids = Array.isArray(data.reportIds) ? data.reportIds : []
          if (
            ids.map(Number).sort((a, b) => a - b).join(',') !==
            reportKeyStr
          ) {
            return
          }
        }
        if (data.success === false || data.reportId === undefined || data.reportId === null) {
          fail(data.error || '报告生成失败')
          return
        }
        succeed(Number(data.reportId))
      },
    })
  })
}

export function useReportCompare() {
  const compare = useCallback(
    async (
      taskIds: number[],
      name?: string,
      config?: ReportCompareConfig
    ): Promise<number> => {
      const result = await compareReports({
        task_ids: taskIds,
        name: name || '对比报告',
        config,
      })
      toast.success('对比报告已生成')
      return result.report_id
    },
    []
  )

  const secondaryCompare = useCallback(
    async (
      reportIds: number[],
      description?: string,
      config?: ReportCompareConfig
    ): Promise<SecondaryCompareResult> => {
      const result = await secondaryCompareReports({
        report_ids: reportIds,
        description: description || undefined,
        config,
      })
      toast.info('二次对比报告生成中，请稍后...')
      return result
    },
    []
  )

  return { compare, secondaryCompare }
}
