/**
 * Realtime frame 订阅（infrastructure/realtime 层；10_测试执行.md §9；INT-646 返修）。
 * §3.7：frame 通道事件不落库，经 EventBus REPORT_EVENTS → api_gateway sse_bp →
 * SSE /sse/events 推送（event 名 realtime_frame）；无 Realtime 设备时该条不渲染。
 * 接线：subscribeSse 订阅 realtime_frame（REPORT_EVENTS 通道），载荷经 frame.dto /
 * frameEventAdapter 转 camelCase 枚举消费；断线重连由 sse.ts 指数退避处理，
 * 本层按 test_case_id+seq 去重（重连重复推送同帧跳过）。
 */
import { useEffect, useRef, useState } from 'react'

import type { RealtimeFrame } from '@/domain/models/testExecution'
import { frameFromDto } from '@/infrastructure/adapters/frameEventAdapter'
import type { FrameEventDto } from '@/infrastructure/dto/frame.dto'
import { SSE_EVENT_CHANNELS, subscribeSse } from '@/infrastructure/realtime/sse'

/**
 * 订阅 Realtime frame 增量（websocket_api 设备选中时启用）。
 * 流开启即挂 SSE 订阅；到达任一事件即 append 一帧。
 */
export function useRealtimeFrameStream(enabled: boolean): RealtimeFrame[] {
  const [frames, setFrames] = useState<RealtimeFrame[]>([])
  const seenRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!enabled) {
      setFrames([])
      seenRef.current.clear()
      return
    }
    const unsubscribe = subscribeSse({
      channels: [SSE_EVENT_CHANNELS.REPORT_EVENTS],
      onEvent: (event) => {
        if (event.eventType !== 'realtime_frame') return
        const dto = event.data as FrameEventDto | null
        if (!dto || typeof dto !== 'object' || !dto.type) return
        const key = `${dto.test_case_id}:${dto.seq ?? ''}`
        if (seenRef.current.has(key)) return
        seenRef.current.add(key)
        setFrames((prev) => [...prev, frameFromDto(dto)])
      },
    })
    return unsubscribe
  }, [enabled])

  return frames
}
