/**
 * 设备状态实时流（application 层；订阅 SSE DEVICE_EVENTS）。
 *
 * 数据链路：device_service 健康检查/设备操作/播放通道检测落状态事件 →
 * EventBus DEVICE_EVENTS（EventType.DEVICE_STATUS_CHANGED）→ api_gateway
 * sse_bp._map_event 以同名事件下发 → 本 hook 收到后失效设备相关 query 重拉列表。
 * 这样物理拔线（监控线程周期健康检查判定离线）、点「断开/健康检查」后，
 * 设备卡/表格不再停留在缓存的「在线」态。
 *
 * 设备事件是整批推送（批量健康检查逐设备一条），按去抖窗口合并成一次失效，
 * 避免一轮检查触发 N 次全量列表重拉。
 */
import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { DEVICE_STATUS_CHANGED_EVENT } from '@/domain/models/device'
import { hasPermission } from '@/domain/models/user'
import { SSE_EVENT_CHANNELS, subscribeSse } from '@/infrastructure/realtime/sse'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/** 同批设备状态事件的合并窗口（ms） */
const INVALIDATE_DEBOUNCE_MS = 300

/** 受设备状态影响的 query 前缀：设备管理页三类列表 + 开始测试页资源列表 */
const DEVICE_QUERY_KEYS: readonly (readonly string[])[] = [
  ['devices'],
  ['test-execution', 'devices'],
]

export function useDeviceStatusStream(): void {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const hasSseRead = hasPermission(user, 'sse:read')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!hasSseRead) return
    const clearTimer = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
    const off = subscribeSse({
      channels: [SSE_EVENT_CHANNELS.DEVICE_EVENTS],
      onEvent: (event) => {
        if (event.eventType !== DEVICE_STATUS_CHANGED_EVENT) return
        clearTimer()
        timerRef.current = setTimeout(() => {
          timerRef.current = null
          for (const queryKey of DEVICE_QUERY_KEYS) {
            void queryClient.invalidateQueries({ queryKey })
          }
        }, INVALIDATE_DEBOUNCE_MS)
      },
    })
    return () => {
      off()
      clearTimer()
    }
  }, [hasSseRead, queryClient])
}
