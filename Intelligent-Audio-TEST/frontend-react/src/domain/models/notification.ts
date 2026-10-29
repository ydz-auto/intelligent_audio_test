/**
 * 通知中心领域模型（domain 层）。
 * 形态对照 api_gateway 通知/公告通道：通知页签 = SSE 事件流（task_progress /
 * report_generated / import_progress / task_log），公告页签 = 站点公告
 * （system_options.site.notice，option API 真实读取）。
 */

export type NotificationTab = 'notice' | 'announcement'

/** 通知行语义类型（色点/图标映射；02_导航栏.md §3.6 定稿） */
export type NotificationKind = 'task' | 'report' | 'import' | 'error'

export type AppNotification = {
  id: string
  tab: NotificationTab
  title: string
  content: string
  /** ISO 时间串 */
  createdAt: string
  read: boolean
  /** 通知行语义类型（色点：任务=info、报告=success、导入=chart-3、错误=destructive） */
  kind?: NotificationKind
  /** 关联任务/报告 id（名称解析与跳转用） */
  taskId?: string
  reportId?: string
  /** 业务去重 key（同 key 事件只保留最新一条；use-notifications 按此替换旧行） */
  dedupeKey?: string
}
