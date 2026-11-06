/**
 * useSlowPending 慢加载探测测试（INT-1280）：
 * fetching 持续超过阈值 → isSlow；完成后复位；restartSlow 重试后重启计时。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  SLOW_CANDIDATES_THRESHOLD_MS,
  useSlowPending,
} from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'

describe('useSlowPending（INT-1280 慢加载探测）', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('fetching 超过阈值 → isSlow；完成后复位', () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(
      ({ fetching }) => useSlowPending(fetching),
      { initialProps: { fetching: true } }
    )
    expect(result.current.isSlow).toBe(false)
    act(() => {
      vi.advanceTimersByTime(SLOW_CANDIDATES_THRESHOLD_MS - 1)
    })
    expect(result.current.isSlow).toBe(false)
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.isSlow).toBe(true)
    act(() => {
      rerender({ fetching: false })
    })
    expect(result.current.isSlow).toBe(false)
  })

  it('restartSlow 复位并重启计时（重试后重新给满阈值）', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSlowPending(true))
    act(() => {
      vi.advanceTimersByTime(SLOW_CANDIDATES_THRESHOLD_MS)
    })
    expect(result.current.isSlow).toBe(true)
    act(() => {
      result.current.restartSlow()
    })
    expect(result.current.isSlow).toBe(false)
    act(() => {
      vi.advanceTimersByTime(SLOW_CANDIDATES_THRESHOLD_MS - 1)
    })
    expect(result.current.isSlow).toBe(false)
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.isSlow).toBe(true)
  })
})
