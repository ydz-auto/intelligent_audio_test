/**
 * 通知中心 infrastructure API（infrastructure/api 层；INT-731 接线）。
 * 数据源对照 02_导航栏.md §3.6：
 * - 通知页签 = SSE 事件流（GET /api/v1/sse/events，sse:read）——复用基座
 *   infrastructure/realtime/sse.ts 的 subscribeSse（断线指数退避重连已有）。
 * - 公告页签 = 站点公告（system_options.site.notice，option API 读取，
 *   复用 optionApi.getSystemOptions；未配置为空态）。
 * - 任务名/报告名：task_progress → 最近任务列表快照（GET /tasks），report_generated →
 *   最近报告列表快照（GET /reports，name 回退 task_name）；快照未命中降级
 *   「任务 #id / 报告 #id」。
 *
 * INT-1227（缺陷·React基座）：真实库栈 SSE 会转发 5000 段开发栈经共享 Redis
 * pub/sub 通道发布的测试事件，其 task_id/report_id 在主库不存在——旧实现对每个
 * 此类事件发 GET /tasks/{id} / /reports/{id}，浏览器记网络 404 SEVERE（「控制台
 * 报错零容忍」红线）。修复：名称解析前先以「最近列表快照」判存在性——快照命中用
 * 真实名；未命中视为不存在，降级「任务 #id / 报告 #id」且不发详情请求（列表查询
 * 本身不会 404，控制台零 SEVERE）。环境层根治（隔离 pub/sub 通道前缀）另开解阻卡。
 */
import { mapSseEventToNotification } from '@/infrastructure/adapters/notificationAdapter'
import {
  subscribeSse,
  SSE_EVENT_CHANNELS,
  type SseEvent,
  type SseStatus,
} from '@/infrastructure/realtime/sse'
import { fetchReportList } from '@/infrastructure/api/reports-api'
import { fetchTaskList } from '@/infrastructure/api/tasks-list-api'
import type { AppNotification } from '@/domain/models/notification'

/** 通知中心订阅通道（TASK + REPORT；CASE/DEVICE/CONFIG 后端暂未映射推送） */
const NOTIFICATION_CHANNELS = [
  SSE_EVENT_CHANNELS.TASK_EVENTS,
  SSE_EVENT_CHANNELS.REPORT_EVENTS,
]

export interface NotificationStreamHandlers {
  onEvent: (item: AppNotification) => void
  onStatusChange?: (status: SseStatus) => void
  signal?: AbortSignal
}

/**
 * 订阅通知事件流：订阅 SSE 五通道中的 TASK/REPORT，经适配器映射为通知行。
 * 返回解绑函数（组件卸载/登出时调用）。
 */
export function subscribeNotificationStream(
  handlers: NotificationStreamHandlers
): () => void {
  return subscribeSse({
    channels: NOTIFICATION_CHANNELS,
    signal: handlers.signal,
    onStatusChange: handlers.onStatusChange,
    onEvent: (event: SseEvent) => {
      const item = mapSseEventToNotification(event)
      if (item) handlers.onEvent(item)
    },
  })
}

/** 名称解析缓存（按 id 去重；只缓存真实名——降级文案不缓存，快照 TTL 刷新后
 * 新建任务/报告仍可补进并解析出真实名，INT-1227 返修） */
const taskNameCache = new Map<string, string>()
const reportNameCache = new Map<string, string>()

function fallbackTaskName(taskId: string): string {
  return `任务 #${taskId}`
}

function fallbackReportName(reportId: string): string {
  return `报告 #${reportId}`
}

/** 最近资源列表快照（id → name），用于名称解析前判存在性（INT-1227）。
 * 快照带 TTL：会话内新建的任务/报告也能在 miss 后补进；拉取失败保留旧快照，
 * 本次按未命中降级、下次解析重试。 */
const NAME_SNAPSHOT_TTL_MS = 60_000

function createNameSnapshotLoader(
  load: () => Promise<Array<{ id: number; name: string }>>
): () => Promise<Map<string, string> | null> {
  let snapshot: Map<string, string> | null = null
  let snapshotAt = 0
  let loading: Promise<Map<string, string> | null> | null = null

  return async function loadSnapshot(): Promise<Map<string, string> | null> {
    if (snapshot && Date.now() - snapshotAt < NAME_SNAPSHOT_TTL_MS) {
      return snapshot
    }
    if (loading) return loading
    loading = (async () => {
      try {
        const items = await load()
        const map = new Map<string, string>()
        for (const item of items) {
          if (item.id != null) map.set(String(item.id), item.name.trim())
        }
        snapshot = map
        snapshotAt = Date.now()
      } catch {
        // 列表拉取失败：保留旧快照（若有），本次按未命中降级
      } finally {
        loading = null
      }
      return snapshot
    })()
    return loading
  }
}

/** 最近任务名快照（created_at 倒序前 100 条；活跃/执行中任务必在其中） */
const loadTaskNames = createNameSnapshotLoader(async () => {
  const { items } = await fetchTaskList({ perPage: 100 })
  return items.map((item) => ({ id: item.id, name: item.name }))
})

/** 最近报告名快照（created_at 倒序前 100 条；name 空回退 task_name） */
const loadReportNames = createNameSnapshotLoader(async () => {
  const data = await fetchReportList({
    page: 1,
    per_page: 100,
    sort_by: 'created_at',
    order: 'desc',
    favorite: false,
    deleted: false,
  })
  return data.items.map((item) => ({
    id: item.id,
    name: item.name.trim() || item.task_name.trim(),
  }))
})

/**
 * 任务名解析（INT-1227）：以最近任务列表快照判存在性，命中用真实名；未命中
 * （环境串扰引用不存在的任务 / 快照外旧任务）降级「任务 #id」——不再发
 * GET /tasks/{id}，杜绝 404 SEVERE 控制台报错。
 * 降级文案不写缓存：快照带 TTL，miss 重查只走内存 Map（无网络开销），会话内
 * 新建任务在快照刷新后仍能解析出真实名。
 */
export async function resolveTaskName(taskId: string): Promise<string> {
  const cached = taskNameCache.get(taskId)
  if (cached) return cached
  const snapshot = await loadTaskNames()
  const name = snapshot?.get(taskId)
  if (name) {
    taskNameCache.set(taskId, name)
    return name
  }
  return fallbackTaskName(taskId)
}

/** 报告名解析（INT-1227 同款防 404）：最近报告列表快照命中用真实名，未命中降级「报告 #id」 */
export async function resolveReportName(reportId: string): Promise<string> {
  const cached = reportNameCache.get(reportId)
  if (cached) return cached
  const snapshot = await loadReportNames()
  const name = snapshot?.get(reportId)
  if (name) {
    reportNameCache.set(reportId, name)
    return name
  }
  return fallbackReportName(reportId)
}

/** 名称解析门控选项（INT-1289：application 层按 hasPermission 传入；
 * 无对应读权限不发起 /tasks、/reports 快照请求，通知行保留「任务 #id / 报告 #id」降级）。 */
export interface ResolveNameOptions {
  /** 允许解析任务名（task:read 门控；false 保留降级标题不发 GET /tasks） */
  task?: boolean
  /** 允许解析报告名（report:read 门控；false 保留降级标题不发 GET /reports） */
  report?: boolean
}

/**
 * 为通知行解析真实名称并返回更新后的通知（名称解析失败保留原降级标题）。
 * 异步批处理由调用方编排（不阻塞事件行渲染，§3.6）。
 * options 缺省 = 全部可解析（兼容既有调用/测试）；应用层按角色权限显式传 false。
 */
export async function resolveNotificationNames(
  item: AppNotification,
  options?: ResolveNameOptions
): Promise<AppNotification> {
  if (item.taskId && item.kind === 'task' && options?.task !== false) {
    const name = await resolveTaskName(item.taskId)
    if (name && !name.startsWith('任务 #')) {
      return { ...item, title: name }
    }
  }
  if (item.reportId && item.kind === 'report' && options?.report !== false) {
    const name = await resolveReportName(item.reportId)
    if (name && !name.startsWith('报告 #')) {
      return { ...item, title: name }
    }
  }
  return item
}
