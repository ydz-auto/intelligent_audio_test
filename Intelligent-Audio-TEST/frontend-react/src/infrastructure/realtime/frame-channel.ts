/**
 * Realtime frame 订阅桩（infrastructure/realtime 层；10_测试执行.md §9）。
 * §3.7：frame 通道事件不落库，Socket.IO room=task_id 推送；无 Realtime 设备时该条不渲染。
 * 红线④：mock 订阅（setInterval 逐条吐出 MOCK_FRAMES）；TODO(API 接线):
 * socket.io room=task_id 订阅 + HTTP 轮询降级（5s，INT-203 口径，复用 taskChannel 世代号）。
 */
import { useEffect, useRef, useState } from 'react'

import type { RealtimeFrame } from '@/domain/models/testExecution'
import { MOCK_FRAMES } from '@/infrastructure/mock/test-execution-mock'

/**
 * 订阅 Realtime frame 增量（websocket_api 设备选中时启用）。
 * mock 态：间隔 900ms 逐条吐出；到达末条后停止并保持。
 */
export function useRealtimeFrameStream(enabled: boolean): RealtimeFrame[] {
  const [frames, setFrames] = useState<RealtimeFrame[]>([])
  const indexRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!enabled) {
      setFrames([])
      indexRef.current = 0
      return
    }
    timerRef.current = setInterval(() => {
      setFrames((prev) => {
        if (indexRef.current >= MOCK_FRAMES.length) {
          if (timerRef.current) clearInterval(timerRef.current)
          return prev
        }
        const next = MOCK_FRAMES[indexRef.current]
        indexRef.current += 1
        return [...prev, next]
      })
    }, 900)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [enabled])

  return frames
}
