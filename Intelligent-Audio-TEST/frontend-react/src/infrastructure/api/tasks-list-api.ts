/**
 * 任务域列表/详情 API 桩（infrastructure 层，09_任务域.md §10）。
 * 全部返回 mock 常量（红线④），接线时替换为真实请求：
 *   GET /api/v1/tasks                  （task.py TaskListQuery：page/per_page/status/
 *       algorithm_type/search/start_date/end_date/favorite/deleted/evaluation_status/
 *       merged/execution_status）
 *   GET /api/v1/tasks/stats?granularity=day  （TaskDomainStatsData，徽章行数据源）
 *   GET /api/v1/published-tasks        （published_task.py PublishedTaskListData）
 *   GET /api/v1/tasks/cherry-picks     （INT-339 §8 契约；后端未落前 hooks 容错禁用入口）
 *   GET /api/v1/tasks/{id}             （TaskDetailData）
 *   GET /api/v1/tasks/{id}/logs        （log.py LogEntry 分页）
 */
import type {
  CherryPickTask,
  PublishedTaskItem,
  TaskDetailData,
  TaskListItem,
  TaskLogEntry,
} from '@/domain/models/task'
import {
  MOCK_CHERRY_PICKS,
  MOCK_MERGED_TASKS,
  MOCK_PUBLISHED_TASKS,
  MOCK_TASK_DETAIL,
  MOCK_TASK_LOGS,
  MOCK_TASKS,
} from '../mock/tasks-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 120))
}

/** 日常任务列表（含收藏/回收站态；mock 不做服务端分页，返回全量） */
export async function fetchTaskList(
  _query: {
    page?: number
    perPage?: number
    search?: string
    executionStatus?: string | null
    evaluationStatus?: string | null
    tags?: string[]
    favorite?: boolean
    trash?: boolean
    algorithmType?: string | null
  }
): Promise<{ items: TaskListItem[]; total: number }> {
  // TODO(API 接线): GET /api/v1/tasks?…
  const { search, executionStatus, evaluationStatus, favorite, trash, tags } =
    _query

  let items = MOCK_TASKS
  if (trash) items = items.filter((t) => t.deleted)
  else items = items.filter((t) => !t.deleted)
  if (favorite) items = items.filter((t) => t.is_favorite)
  if (search) {
    const keyword = search.trim().toLowerCase()
    items = items.filter(
      (t) =>
        t.name.toLowerCase().includes(keyword) ||
        (t.description ?? '').toLowerCase().includes(keyword) ||
        t.tags.some((tag) => tag.toLowerCase().includes(keyword))
    )
  }
  if (executionStatus)
    items = items.filter((t) => t.execution_status === executionStatus)
  if (evaluationStatus)
    items = items.filter((t) => t.evaluation_status === evaluationStatus)
  if (tags && tags.length > 0)
    items = items.filter((t) => tags.every((tag) => t.tags.includes(tag)))

  return mockLatency({ items, total: items.length })
}

/** 已发布任务列表（mock 全量返回） */
export async function fetchPublishedTaskList(
  _query: { search?: string; type?: string | null; ptStatus?: string | null }
): Promise<{ items: PublishedTaskItem[]; total: number }> {
  // TODO(API 接线): GET /api/v1/published-tasks
  const { search, type, ptStatus } = _query
  let items = MOCK_PUBLISHED_TASKS
  if (search) {
    const keyword = search.trim().toLowerCase()
    items = items.filter(
      (t) =>
        t.name.toLowerCase().includes(keyword) ||
        (t.description ?? '').toLowerCase().includes(keyword)
    )
  }
  if (type) items = items.filter((t) => t.type === type)
  if (ptStatus) items = items.filter((t) => t.status === ptStatus)
  return mockLatency({ items, total: items.length })
}

/** 合并任务列表（mock：MOCK_TASKS 中 status=merged 的集合） */
export async function fetchMergedTaskList(
  _query: { search?: string }
): Promise<{ items: TaskListItem[]; total: number }> {
  // TODO(API 接线): GET /api/v1/tasks?merged=true
  const { search } = _query
  let items = MOCK_MERGED_TASKS
  if (search) {
    const keyword = search.trim().toLowerCase()
    items = items.filter((t) => t.name.toLowerCase().includes(keyword))
  }
  return mockLatency({ items, total: items.length })
}

/** 挑选合并任务列表（后端未落前返回 mock，入口不禁用） */
export async function fetchCherryPickList(
  _query: { search?: string }
): Promise<{ items: CherryPickTask[]; total: number }> {
  // TODO(API 接线): GET /api/v1/tasks/cherry-picks
  const { search } = _query
  let items = MOCK_CHERRY_PICKS
  if (search) {
    const keyword = search.trim().toLowerCase()
    items = items.filter((t) => t.name.toLowerCase().includes(keyword))
  }
  return mockLatency({ items, total: items.length })
}

/** 任务详情（路由页 /tasks/:id 与快览弹窗共用同一数据源） */
export async function fetchTaskDetail(
  taskId: number
): Promise<TaskDetailData> {
  // TODO(API 接线): GET /api/v1/tasks/{id}
  return mockLatency({ ...MOCK_TASK_DETAIL, id: taskId })
}

/** 实时日志（mock 分页：page+1=更老；新→老） */
export async function fetchTaskLogs(
  _taskId: number,
  _page = 1,
  _pageSize = 20
): Promise<TaskLogEntry[]> {
  // TODO(API 接线): GET /api/v1/tasks/{id}/logs?page=&page_size=
  return mockLatency(MOCK_TASK_LOGS)
}
