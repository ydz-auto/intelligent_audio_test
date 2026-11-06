/**
 * 通知中心已读标记 store（infrastructure/stores 层；INT-731 接线）。
 * 未读机制对照 02_导航栏.md §3.6（newAPI useNotificationStore 照搬）：
 * - 通知页签：localStorage 已读标记 `iatp:notify:v1:last-read-event`（最新事件键比对）
 * - 公告页签：`iatp:notify:v1:read-ids`（公告逐条）
 * 打开面板即写当前页签已读；未读数 = 两页签之和。
 */
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

type NotificationReadState = {
  /** 已读通知事件的最大序号（会话内 SSE 事件按到达序递增；持久化跨会话） */
  lastReadEventSeq: number
  /** 已读公告 id 集合（站点公告内容哈希） */
  readAnnouncementIds: string[]
  markEventsRead: (seq: number) => void
  markAnnouncementRead: (id: string) => void
  isAnnouncementRead: (id: string) => boolean
}

export const useNotificationReadStore = create<NotificationReadState>()(
  persist(
    (set, get) => ({
      lastReadEventSeq: 0,
      readAnnouncementIds: [],
      markEventsRead: (seq) =>
        set((state) => ({
          lastReadEventSeq: Math.max(state.lastReadEventSeq, seq),
        })),
      markAnnouncementRead: (id) =>
        set((state) =>
          state.readAnnouncementIds.includes(id)
            ? state
            : { readAnnouncementIds: [...state.readAnnouncementIds, id] }
        ),
      isAnnouncementRead: (id) => get().readAnnouncementIds.includes(id),
    }),
    {
      name: 'iatp:notify:v1',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        lastReadEventSeq: state.lastReadEventSeq,
        readAnnouncementIds: state.readAnnouncementIds,
      }),
    }
  )
)
