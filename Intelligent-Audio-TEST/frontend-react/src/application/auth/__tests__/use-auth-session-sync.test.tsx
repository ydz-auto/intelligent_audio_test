/**
 * 登录会话权限同步：定时兜底刷新 + 标签页切回可见立即刷新，卸载后停止。
 * 权限调整后前端菜单/按钮无需重新登录即可更新。
 */
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AUTH_SESSION_SYNC_INTERVAL_MS,
  useAuthSessionSync,
} from '@/application/auth/use-auth-session-sync'

const { refreshMock } = vi.hoisted(() => ({ refreshMock: vi.fn() }))

vi.mock('@/infrastructure/stores/auth-store', () => ({
  refreshAuthSession: refreshMock,
}))

function Harness() {
  useAuthSessionSync()
  return null
}

beforeEach(() => {
  vi.useFakeTimers()
  refreshMock.mockReset()
  refreshMock.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useAuthSessionSync 权限同步', () => {
  it('定时器按同步间隔静默刷新会话', async () => {
    render(<Harness />)

    await act(async () => {
      vi.advanceTimersByTime(AUTH_SESSION_SYNC_INTERVAL_MS)
    })

    expect(refreshMock).toHaveBeenCalledTimes(1)
  })

  it('标签页切回可见时立即刷新会话', async () => {
    render(<Harness />)

    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(refreshMock).toHaveBeenCalledTimes(1)
  })

  it('组件卸载后不再定时刷新', async () => {
    const { unmount } = render(<Harness />)
    unmount()

    await act(async () => {
      vi.advanceTimersByTime(AUTH_SESSION_SYNC_INTERVAL_MS)
    })

    expect(refreshMock).not.toHaveBeenCalled()
  })
})
