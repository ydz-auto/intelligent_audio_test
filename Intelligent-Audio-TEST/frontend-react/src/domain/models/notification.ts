/**
 * 通知中心领域模型（domain 层）。
 * 形态对照 api_gateway 通知/公告通道；TODO(API 接线): SSE 事件推送替换 mock。
 */

export type NotificationTab = 'notice' | 'announcement'

export type AppNotification = {
  id: string
  tab: NotificationTab
  title: string
  content: string
  /** ISO 时间串 */
  createdAt: string
  read: boolean
}

/** 红线④：mock 常量 */
export const MOCK_NOTIFICATIONS: AppNotification[] = [
  {
    id: 'n-001',
    tab: 'notice',
    title: '任务执行完成',
    content: '任务「回归测试-第 12 轮」已完成，可前往报告中心查看结果。',
    createdAt: '2026-10-15T09:30:00+08:00',
    read: false,
  },
  {
    id: 'n-002',
    tab: 'notice',
    title: '设备离线提醒',
    content: '设备「会议室 A 人工头」超过 10 分钟未上报心跳。',
    createdAt: '2026-10-15T08:12:00+08:00',
    read: false,
  },
  {
    id: 'n-003',
    tab: 'notice',
    title: '用例导入完成',
    content: '批量导入 36 条用例成功，2 条因格式问题跳过。',
    createdAt: '2026-10-14T17:45:00+08:00',
    read: true,
  },
  {
    id: 'a-001',
    tab: 'announcement',
    title: '平台维护公告',
    content: '本周六 02:00-04:00 进行算法服务升级，期间任务下发将短暂受限。',
    createdAt: '2026-10-13T10:00:00+08:00',
    read: false,
  },
  {
    id: 'a-002',
    tab: 'announcement',
    title: '新版报告中心上线',
    content: '报告中心新增历史报告页签，旧链接自动重定向。',
    createdAt: '2026-10-10T14:20:00+08:00',
    read: true,
  },
]
