/**
 * 任务域列表/详情/日志 API（infrastructure/api 层，接线基座 INT-605 client.ts 出口；
 * 09_任务域.md §10 契约，INT-623 Vue 侧已比对后端契约）。
 *   GET /api/v1/tasks                 （task_bp.py TaskListQuery：page/per_page/status/
 *       algorithm_type/search/start_date/end_date/favorite/deleted/evaluation_status/merged/
 *       cherry_pick/execution_status；tags 后端未支持 → 客户端近似过滤，FEAT 证据见 INT-638）
 *   GET /api/v1/published-tasks       （published_task_bp.py：page/per_page/status/keyword/type）
 *   GET /api/v1/tasks?merged=true     （合并容器，§11-1 客户端双查询合并）
 *   GET /api/v1/tasks?cherry_pick=true（挑选合并容器，INT-339 §8）
 *   GET /api/v1/tasks/{id}            （TaskDetailData）
 *   GET /api/v1/logs?task_id=&page=&per_page=（log_bp.py 任务日志，LogEntry 分页；
 *       /tasks/{id}/logs 端点不存在，按 INT-81 业务日志合并视图）
 */
import type { CherryPickContainer } from '@/domain/models/cherryPick'
import type {
  CherryPickTask,
  PublishedTaskDetail,
  PublishedTaskItem,
  TaskDetailData,
  TaskListItem,
  TaskLogEntry,
} from '@/domain/models/task'
import {
  toCherryPickContainer,
  toCherryPickTask,
  toPublishedTaskDetail,
  toPublishedTaskListPage,
  toTaskDetail,
  toTaskListPage,
  toTaskLogEntry,
} from '@/infrastructure/adapters/dto/task-adapter'
import { request } from '@/infrastructure/api/client'
import type {
  PaginatedDto,
  PublishedTaskDetailDto,
  PublishedTaskItemDto,
  TaskDetailDto,
  TaskListItemDto,
  TaskLogEntryDto,
} from '@/infrastructure/dto/task.dto'

export interface TaskListQuery {
  page?: number
  perPage?: number
  search?: string
  executionStatus?: string | null
  evaluationStatus?: string | null
  tags?: string[]
  favorite?: boolean
  trash?: boolean
  algorithmType?: string | null
  /** 创建时间范围（映射后端 start_date/end_date；YYYY-MM-DD 或 ISO，照旧 Vue startTime/endTime 口径） */
  startDate?: string | null
  endDate?: string | null
}

/**
 * 日常任务列表（含收藏/回收站态；服务端分页，per_page 默认 100 近似视觉稿全量，
 * URL 化分页随 09_任务域.md §3.11 接线后续卡）。
 */
export async function fetchTaskList(
  query: TaskListQuery = {}
): Promise<{ items: TaskListItem[]; total: number }> {
  const params: Record<string, unknown> = {
    page: query.page ?? 1,
    per_page: query.perPage ?? 100,
  }
  if (query.search) params.search = query.search
  if (query.algorithmType) params.algorithm_type = query.algorithmType
  if (query.executionStatus) params.execution_status = query.executionStatus
  if (query.evaluationStatus) params.evaluation_status = query.evaluationStatus
  // INT-141：收藏 / 回收站过滤（同名透传；后端 TaskListQuery.favorite/deleted）
  if (query.favorite) params.favorite = true
  if (query.trash) params.deleted = true
  // 创建时间范围（旧 Vue startTime/endTime → 后端 start_date/end_date；TaskListQuery 实测支持）
  if (query.startDate) params.start_date = query.startDate
  if (query.endDate) params.end_date = query.endDate

  const dto = await request<PaginatedDto<TaskListItemDto>>(
    'GET',
    '/tasks',
    undefined,
    { params }
  )
  const items = toTaskListPage(dto)
  // tags 后端 TaskListQuery 未支持（无 tags 参数）：在返回页上近似过滤（分页下仅对当前页生效）
  const tags = query.tags?.filter(Boolean)
  if (tags && tags.length > 0) {
    items.items = items.items.filter((t) => tags.every((tag) => t.tags.includes(tag)))
  }
  return items
}

/** 已发布任务列表（keyword/type/status 服务端筛选；per_page 默认 100） */
export async function fetchPublishedTaskList(
  query: {
    page?: number
    perPage?: number
    search?: string
    type?: string | null
    ptStatus?: string | null
  } = {}
): Promise<{ items: PublishedTaskItem[]; total: number }> {
  const params: Record<string, unknown> = {
    page: query.page ?? 1,
    per_page: query.perPage ?? 100,
  }
  if (query.search) params.keyword = query.search
  if (query.type && query.type !== 'all') params.type = query.type
  if (query.ptStatus && query.ptStatus !== 'all') params.status = query.ptStatus

  const dto = await request<PaginatedDto<PublishedTaskItemDto>>(
    'GET',
    '/published-tasks',
    undefined,
    { params }
  )
  return toPublishedTaskListPage(dto)
}

/** 已发布任务详情（GET /published-tasks/{id}；展开版本链行数据源，真实版本历史/冻结快照） */
export async function fetchPublishedTaskDetail(
  publishedTaskId: number
): Promise<PublishedTaskDetail> {
  const dto = await request<PublishedTaskDetailDto>(
    'GET',
    `/published-tasks/${publishedTaskId}`
  )
  return toPublishedTaskDetail(dto)
}

/** 发布已发布任务入参（published_task.py PublishedTaskCreateRequest snake_case 契约） */
export interface PublishTaskInput {
  sourceTaskId: number
  name: string
  description?: string | null
  publishReason?: string | null
  benchmark?: boolean
  benchmarkSuite?: string | null
  benchmarkCategory?: string | null
}

/** 发布已发布任务（POST /published-tasks；返回 201 IdData{ id }） */
export async function publishTask(input: PublishTaskInput): Promise<{ id: number }> {
  const dto = await request<{ id: number }>('POST', '/published-tasks', {
    source_task_id: input.sourceTaskId,
    name: input.name,
    description: input.description ?? null,
    publish_reason: input.publishReason ?? null,
    benchmark: input.benchmark ?? false,
    benchmark_suite: input.benchmarkSuite ?? null,
    benchmark_category: input.benchmarkCategory ?? null,
  })
  return { id: dto.id }
}

/** 合并任务列表（GET /tasks?merged=true；整任务合并容器数据源） */
export async function fetchMergedTaskList(
  query: { search?: string } = {}
): Promise<{ items: CherryPickContainer[]; total: number }> {
  const params: Record<string, unknown> = { page: 1, per_page: 100, merged: true }
  if (query.search) params.search = query.search
  const dto = await request<PaginatedDto<TaskListItemDto>>(
    'GET',
    '/tasks',
    undefined,
    { params }
  )
  return {
    items: (dto.items ?? []).map(toCherryPickContainer),
    total: dto.total ?? 0,
  }
}

/** 挑选合并任务列表（GET /tasks?cherry_pick=true；INT-339 §8 契约） */
export async function fetchCherryPickList(
  query: { search?: string } = {}
): Promise<{ items: CherryPickTask[]; total: number }> {
  const params: Record<string, unknown> = { page: 1, per_page: 100, cherry_pick: true }
  if (query.search) params.search = query.search
  const dto = await request<PaginatedDto<TaskListItemDto>>(
    'GET',
    '/tasks',
    undefined,
    { params }
  )
  return {
    items: (dto.items ?? []).map(toCherryPickTask),
    total: dto.total ?? 0,
  }
}

/** 任务详情（路由页 /tasks/:id 与快览弹窗共用同一数据源） */
export async function fetchTaskDetail(taskId: number): Promise<TaskDetailData> {
  const dto = await request<TaskDetailDto>('GET', `/tasks/${taskId}`)
  return toTaskDetail(dto)
}

/** 任务实时日志（GET /logs?task_id= 分页；page+1=更老，新→老） */
export async function fetchTaskLogs(
  taskId: number,
  page = 1,
  pageSize = 20
): Promise<TaskLogEntry[]> {
  const dto = await request<PaginatedDto<TaskLogEntryDto>>(
    'GET',
    '/logs',
    undefined,
    { params: { task_id: taskId, page, per_page: pageSize } }
  )
  return (dto.items ?? []).map(toTaskLogEntry)
}
