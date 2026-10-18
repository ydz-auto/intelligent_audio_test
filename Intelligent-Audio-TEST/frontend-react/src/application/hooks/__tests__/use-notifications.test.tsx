/**
 * useNotifications 通知中心 hook 单测（INT-731 返修回归）：
 * - P3-1：会话内事件序号以持久已读基线为初始值 → 刷新后新事件不被旧持久值吞掉
 * - P3-2：公告已读 id = 内容哈希 → 内容更新自然生成新 id、重新提示未读
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import type { Mock } from 'vitest'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useNotifications } from '@/application/hooks/use-notifications'
import { useSystemOptions } from '@/application/settings/use-system-options'
import {
  resolveNotificationNames,
  subscribeNotificationStream,
} from '@/infrastructure/api/notificationApi'
import { useNotificationReadStore } from '@/infrastructure/stores/notification-read-store'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import type { AppNotification } from '@/domain/models/notification'

vi.mock('@/application/settings/use-system-options', () => ({
  useSystemOptions: vi.fn(),
}))

vi.mock('@/infrastructure/api/notificationApi', () => ({
  subscribeNotificationStream: vi.fn(),
  resolveNotificationNames: vi.fn(),
}))

const mockSubscribe = subscribeNotificationStream as Mock
const mockResolveNames = resolveNotificationNames as Mock
const mockUseSystemOptions = useSystemOptions as Mock

function makeUser(permissions: string[]) {
  return {
    id: '1',
    username: 'u',
    displayName: 'u',
    roleName: '',
    permissions,
  }
}

function makeEvent(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 'task:1:2026-10-18T16:00:00Z',
    tab: 'notice',
    kind: 'task',
    title: '任务 #1',
    content: '进度 50%',
    createdAt: '2026-10-18T16:00:00Z',
    read: false,
    taskId: '1',
    ...overrides,
  }
}

describe('useNotifications', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: makeUser(['sse:read']) })
    useNotificationReadStore.setState({
      lastReadEventSeq: 0,
      readAnnouncementIds: [],
    })
    localStorage.clear()
    mockUseSystemOptions.mockReturnValue({
      data: { 'site.notice': '' },
      isLoading: false,
    })
    mockSubscribe.mockReset()
    mockSubscribe.mockReturnValue(() => {})
    mockResolveNames.mockReset()
    mockResolveNames.mockResolvedValue(makeEvent())
  })

  it('P3-1：刷新后事件序号以持久已读基线起步，新事件正确计入未读', async () => {
    useNotificationReadStore.setState({ lastReadEventSeq: 5 })
    const { result } = renderHook(() => useNotifications())

    // 新会话事件到达（seq 从基线 5 递增 → 6 > 5）
    const handlers = mockSubscribe.mock.calls[0][0]
    act(() => {
      handlers.onEvent(makeEvent())
    })

    await waitFor(() => expect(result.current.unreadCount).toBe(1))
    expect(result.current.notice[0].id.startsWith('6:')).toBe(true)

    // 打开面板 → 写已读 → 角标清零
    act(() => result.current.setPopoverOpen(true))
    await waitFor(() => expect(result.current.unreadCount).toBe(0))
  })

  it('P3-2：公告已读 id = 内容哈希，内容更新后重新提示未读', async () => {
    mockUseSystemOptions.mockReturnValue({
      data: { 'site.notice': '公告A' },
      isLoading: false,
    })
    const { result, rerender } = renderHook(() => useNotifications())

    await waitFor(() => expect(result.current.announcements).toHaveLength(1))
    const idA = result.current.announcements[0].id
    expect(idA).toMatch(/^site-notice:/)
    expect(result.current.unreadCount).toBe(1)

    // 打开公告页签即写已读 → 清零
    act(() => result.current.setActiveTab('announcement'))
    await waitFor(() => expect(result.current.unreadCount).toBe(0))

    // 站点公告内容更新 → 内容哈希变新 id → 重新未读
    mockUseSystemOptions.mockReturnValue({
      data: { 'site.notice': '公告B' },
      isLoading: false,
    })
    rerender()
    await waitFor(() => expect(result.current.announcements).toHaveLength(1))
    const idB = result.current.announcements[0].id
    expect(idB).not.toBe(idA)
    expect(result.current.unreadCount).toBe(1)
  })
})
