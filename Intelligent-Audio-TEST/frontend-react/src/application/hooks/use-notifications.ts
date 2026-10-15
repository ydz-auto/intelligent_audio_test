import { useMemo, useState } from 'react'

import type {
  AppNotification,
  NotificationTab,
} from '@/domain/models/notification'
import { MOCK_NOTIFICATIONS } from '@/domain/models/notification'

/**
 * 通知中心状态（application 层）。
 * 红线④：mock 常量。TODO(API 接线): 接 SSE 通知通道 + 已读接口替换。
 */
export function useNotifications() {
  const [popoverOpen, setPopoverOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<NotificationTab>('notice')
  // mock 数据同步可得；真实接口接 SSE 后变为加载态
  const loading = false

  const notice = useMemo(
    () => MOCK_NOTIFICATIONS.filter((n) => n.tab === 'notice'),
    []
  )
  const announcements = useMemo(
    () => MOCK_NOTIFICATIONS.filter((n) => n.tab === 'announcement'),
    []
  )
  const unreadCount = useMemo(
    () => MOCK_NOTIFICATIONS.filter((n) => !n.read).length,
    []
  )

  return {
    popoverOpen,
    setPopoverOpen,
    activeTab,
    setActiveTab,
    notice,
    announcements,
    unreadCount,
    loading,
  }
}

export type UseNotificationsReturn = ReturnType<typeof useNotifications>
export type { AppNotification, NotificationTab }
