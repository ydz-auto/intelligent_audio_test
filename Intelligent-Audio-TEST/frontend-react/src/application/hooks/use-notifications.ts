import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  resolveNotificationNames,
  subscribeNotificationStream,
} from '@/infrastructure/api/notificationApi'
import { useSystemOptions } from '@/application/settings/use-system-options'
import {
  useNotificationReadStore,
} from '@/infrastructure/stores/notification-read-store'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { hasPermission } from '@/domain/models/user'
import { resolveSiteNoticeSettings } from '@/domain/models/option'
import type {
  AppNotification,
  NotificationTab,
} from '@/domain/models/notification'
import type { SseStatus } from '@/infrastructure/realtime/sse'

/** 会话内通知列表上界（SSE 事件流只增不减，防止无界堆积） */
const MAX_NOTICE_ITEMS = 50

/** 站点公告行 id（read-ids 比对用） */
const ANNOUNCEMENT_ID = 'site-notice'

/**
 * 通知中心状态（application 层；INT-731 接线）。
 * 数据源真实化：
 * - 通知页签 = SSE 事件流（subscribeNotificationStream → sse:read）
 * - 公告页签 = 站点公告（system_options.site.notice，option API）
 * 未读机制照搬 02_导航栏.md §3.6（localStorage 已读标记，两页签之和）。
 */
export function useNotifications() {
  const [popoverOpen, setPopoverOpenState] = useState(false)
  const [activeTab, setActiveTabState] = useState<NotificationTab>('notice')
  const [notice, setNotice] = useState<AppNotification[]>([])
  const [sseStatus, setSseStatus] = useState<SseStatus>('connecting')

  const user = useAuthStore((s) => s.user)
  const hasSseRead = hasPermission(user, 'sse:read')

  const {
    lastReadEventSeq,
    readAnnouncementIds,
    markEventsRead,
    markAnnouncementRead,
    isAnnouncementRead,
  } = useNotificationReadStore()

  /** 会话内事件序号（未读比对：最新事件键） */
  const eventSeqRef = useRef(0)

  // ===== 通知页签：SSE 事件流 =====
  useEffect(() => {
    if (!hasSseRead) return
    const off = subscribeNotificationStream({
      onStatusChange: (status) => setSseStatus(status),
      onEvent: (raw) => {
        eventSeqRef.current += 1
        const seq = eventSeqRef.current
        const item: AppNotification = { ...raw, id: `${seq}:${raw.id}` }
        setNotice((prev) => [item, ...prev].slice(0, MAX_NOTICE_ITEMS))
        // 名称解析不阻塞行渲染：先以 id 占位，解析完成局部更新
        void resolveNotificationNames(item).then((resolved) => {
          if (resolved.title === item.title) return
          setNotice((prev) =>
            prev.map((n) => (n.id === item.id ? { ...n, title: resolved.title } : n))
          )
        })
      },
    })
    return off
  }, [hasSseRead])

  // ===== 公告页签：站点公告（site.notice）=====
  const { data: options, isLoading: optionsLoading } = useSystemOptions()
  const noticeContent = useMemo(
    () => resolveSiteNoticeSettings(options).notice.trim(),
    [options]
  )

  const announcements = useMemo<AppNotification[]>(() => {
    if (!noticeContent) return []
    return [
      {
        id: ANNOUNCEMENT_ID,
        tab: 'announcement',
        title: '站点公告',
        content: noticeContent,
        createdAt: '',
        read: isAnnouncementRead(ANNOUNCEMENT_ID),
        kind: 'task',
      },
    ]
  }, [noticeContent, isAnnouncementRead])

  // ===== 未读数 = 两页签之和 =====
  const unreadCount = useMemo(() => {
    const noticeUnread = notice.filter((n) => {
      const seq = Number.parseInt(n.id.split(':')[0] ?? '0', 10)
      return seq > lastReadEventSeq
    }).length
    const announcementUnread = noticeContent && !isAnnouncementRead(ANNOUNCEMENT_ID) ? 1 : 0
    return noticeUnread + announcementUnread
  }, [notice, lastReadEventSeq, noticeContent, isAnnouncementRead])

  const loading = useMemo(
    () => (hasSseRead ? sseStatus === 'connecting' || sseStatus === 'reconnecting' : false) || optionsLoading,
    [hasSseRead, sseStatus, optionsLoading]
  )

  // ===== 已读动作 =====
  const markAllRead = useCallback(() => {
    markEventsRead(eventSeqRef.current)
    if (noticeContent) markAnnouncementRead(ANNOUNCEMENT_ID)
  }, [markEventsRead, markAnnouncementRead, noticeContent])

  const setPopoverOpen = useCallback(
    (open: boolean) => {
      setPopoverOpenState(open)
      if (open) {
        // 打开面板即写当前页签已读（§3.6）
        if (activeTab === 'notice') {
          markEventsRead(eventSeqRef.current)
        } else {
          if (noticeContent) markAnnouncementRead(ANNOUNCEMENT_ID)
        }
      }
    },
    [activeTab, markEventsRead, markAnnouncementRead, noticeContent]
  )

  const setActiveTab = useCallback(
    (tab: NotificationTab) => {
      setActiveTabState(tab)
      // 切换页签即写该页签已读（newAPI handleTabChange 语义）
      if (tab === 'notice') {
        markEventsRead(eventSeqRef.current)
      } else {
        if (noticeContent) markAnnouncementRead(ANNOUNCEMENT_ID)
      }
    },
    [markEventsRead, markAnnouncementRead, noticeContent]
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
    markAllRead,
  }
}

export type UseNotificationsReturn = ReturnType<typeof useNotifications>
export type { AppNotification, NotificationTab }
