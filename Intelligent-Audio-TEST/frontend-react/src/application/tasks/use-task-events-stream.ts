/**
 * 任务状态实时流（application 层；订阅 SSE TASK_EVENTS）。
 *
 * 数据链路：task_service 执行进度落库后经 EventBus TASK_EVENTS / task_progress 发布 →
 * api_gateway sse_bp._map_event 以 task_progress 下发 → 本 hook 收到后失效 ['tasks']
 * 前缀缓存（列表 / 详情 / 日志同源）。
 *
 * 背景：任务由执行引擎异步推进，列表没有推送通道也没有轮询，任务跑完后徽章会一直停在
 * 「执行中」，只能手动刷新页面。这里按 task_progress 的状态签名（status /
 * execution_status / evaluation_status）判断是否真的变了，只在状态迁移时失效，
 * 避免每推进一个用例就全量重拉列表。
 */
import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { hasPermission } from '@/domain/models/user'
import { SSE_EVENT_CHANNELS } from '@/infrastructure/realtime/sse'
import { subscribeSharedSse } from '@/infrastructure/realtime/sse-bus'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/** 同批任务状态事件的合并窗口（ms） */
const INVALIDATE_DEBOUNCE_MS = 400

/** task_progress 事件 data（TaskProgressPayload snake_case 子集） */
interface TaskProgressEventData {
  task_id?: string | number
  status?: string
  execution_status?: string
  evaluation_status?: string
}

function toStatusSignature(data: TaskProgressEventData): string {
  return `${data.status ?? ''}|${data.execution_status ?? ''}|${data.evaluation_status ?? ''}`
}

export function useTaskEventsStream(): void {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const hasSseRead = hasPermission(user, 'sse:read')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** task_id → 最近一次已知状态签名（跨断线保留：重连补到的事件仍能识别状态迁移） */
  const statusRef = useRef(new Map<string, string>())

  useEffect(() => {
    if (!hasSseRead) return
    const clearTimer = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
    const scheduleInvalidate = () => {
      clearTimer()
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      }, INVALIDATE_DEBOUNCE_MS)
    }
    const off = subscribeSharedSse({
      channels: [SSE_EVENT_CHANNELS.TASK_EVENTS],
      onEvent: (event) => {
        if (event.eventType !== 'task_progress') return
        const data = event.data as TaskProgressEventData | null
        if (!data || data.task_id === undefined || data.task_id === null) return
        const taskId = String(data.task_id)
        const signature = toStatusSignature(data)
        const known = statusRef.current.get(taskId)
        statusRef.current.set(taskId, signature)
        // 首次见到该任务或状态签名变化才刷新；仅进度推进（alive 同签名）不重拉列表
        if (known === signature) return
        scheduleInvalidate()
      },
    })
    return () => {
      off()
      clearTimer()
    }
  }, [hasSseRead, queryClient])
}
