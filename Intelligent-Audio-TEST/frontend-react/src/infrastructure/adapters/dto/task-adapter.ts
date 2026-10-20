/**
 * 任务域 DTO→Domain 转换器（infrastructure/adapters/dto，09_任务域.md §10）。
 * domain/models/task.ts 任务域模型与 task.py 契约同构（snake_case 字段），
 * 本层仅补派生字段：api_count（apis.length）、source_task_count/source_task_ids
 * （合并/挑选容器）、concurrency（config.concurrency）。
 * 已发布任务（PublishedTaskItemDto）与日志行（TaskLogEntryDto）为纯透传。
 */
import type { CherryPickContainer } from '@/domain/models/cherryPick'
import type {
  CherryPickTask,
  PublishedTaskDetail,
  PublishedTaskItem,
  TaskDetailData,
  TaskListItem,
  TaskLogEntry,
  TaskReevaluateResult,
  TaskRetryResult,
} from '@/domain/models/task'
import type {
  PaginatedDto,
  PublishedTaskDetailDto,
  PublishedTaskItemDto,
  TaskDetailDto,
  TaskListItemDto,
  TaskLogEntryDto,
  TaskReevaluateResultDto,
  TaskRetryResultDto,
} from '@/infrastructure/dto/task.dto'

/** TaskListItem：后端同构字段 + api_count 派生 */
export function toTaskListItem(dto: TaskListItemDto): TaskListItem {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    status: dto.status,
    execution_status: dto.execution_status as TaskListItem['execution_status'],
    evaluation_status: dto.evaluation_status as TaskListItem['evaluation_status'],
    device_types: dto.device_types ?? [],
    config: dto.config ?? {},
    algorithm_type: dto.algorithm_type,
    algorithm_params: dto.algorithm_params,
    started_at: dto.started_at,
    completed_at: dto.completed_at,
    total_cases: dto.total_cases,
    case_count: dto.case_count ?? dto.total_cases,
    device_count: dto.device_count,
    completed_cases: dto.completed_cases,
    failed_cases: dto.failed_cases,
    api_count: (dto.apis ?? []).length,
    tags: dto.tags ?? [],
    created_at: dto.created_at,
    updated_at: dto.updated_at,
    is_favorite: dto.is_favorite,
    deleted: dto.deleted,
    deleted_at: dto.deleted_at,
    deleted_by_user_id: dto.deleted_by_user_id,
    reports: dto.reports,
    devices: dto.devices ?? [],
    apis: dto.apis ?? [],
    source_tasks: dto.source_tasks ?? [],
  }
}

/** 分页任务列表 → { items, total }（消费侧 useTasksList 口径） */
export function toTaskListPage(
  dto: PaginatedDto<TaskListItemDto>
): { items: TaskListItem[]; total: number } {
  return {
    items: (dto.items ?? []).map(toTaskListItem),
    total: dto.total ?? 0,
  }
}

/** TaskDetail：后端同构字段 + api_count/concurrency 派生 */
export function toTaskDetail(dto: TaskDetailDto): TaskDetailData {
  const config = dto.config ?? {}
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    status: dto.status,
    execution_status: dto.execution_status as TaskDetailData['execution_status'],
    evaluation_status: dto.evaluation_status as TaskDetailData['evaluation_status'],
    device_types: dto.device_types ?? [],
    config,
    algorithm_type: dto.algorithm_type,
    algorithm_params: dto.algorithm_params,
    started_at: dto.started_at,
    completed_at: dto.completed_at,
    expected_total_time: dto.expected_total_time,
    expected_complete_time: dto.expected_complete_time,
    used_time: dto.used_time,
    total_cases: dto.total_cases,
    case_count: dto.case_count ?? dto.total_cases,
    device_count: dto.device_count,
    completed_cases: dto.completed_cases,
    failed_cases: dto.failed_cases,
    api_count: (dto.apis ?? []).length,
    concurrency:
      typeof config.concurrency === 'number' ? config.concurrency : null,
    tags: dto.tags ?? [],
    cases: (dto.cases ?? []).map((c) => ({ ...c, reviewed: c.reviewed ?? false })),
    devices: dto.devices ?? [],
    apis: dto.apis ?? [],
    created_at: dto.created_at,
    updated_at: dto.updated_at,
    review_count: dto.review_count ?? 0,
  }
}

/** 已发布任务列表项：纯透传 */
export function toPublishedTaskItem(dto: PublishedTaskItemDto): PublishedTaskItem {
  return { ...dto }
}

/** 已发布任务分页列表 → { items, total } */
export function toPublishedTaskListPage(
  dto: PaginatedDto<PublishedTaskItemDto>
): { items: PublishedTaskItem[]; total: number } {
  return {
    items: (dto.items ?? []).map(toPublishedTaskItem),
    total: dto.total ?? 0,
  }
}

/** 已发布任务详情（GET /published-tasks/{id} → PublishedTaskDetail；纯透传 + versions 行转换） */
export function toPublishedTaskDetail(dto: PublishedTaskDetailDto): PublishedTaskDetail {
  return {
    ...dto,
    versions: (dto.versions ?? []).map(toPublishedTaskItem),
  }
}

/** 挑选合并任务（GET /tasks?cherry_pick=true 行 → CherryPickTask，INT-339 §8 契约） */
export function toCherryPickTask(dto: TaskListItemDto): CherryPickTask {
  const sourceTasks = dto.source_tasks ?? []
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    status: dto.status,
    execution_status: (dto.execution_status ?? 'pending') as CherryPickTask['execution_status'],
    evaluation_status: (dto.evaluation_status ?? 'pending') as CherryPickTask['evaluation_status'],
    total_cases: dto.total_cases,
    source_task_count: sourceTasks.length,
    source_task_ids: sourceTasks.map((t) => t.id),
    created_at: dto.created_at,
    is_favorite: dto.is_favorite,
  }
}

/**
 * 统一合并容器（GET /tasks?merged=true ∪ ?cherry_pick=true 双查询行 → CherryPickContainer，
 * §11-1 落地前客户端双查询合并）。merge_type 派生：is_cherry_pick=true → picked，
 * 否则（status=merged）→ whole；source_result_count 后端列表行未返，以 total_cases 近似。
 */
export function toCherryPickContainer(
  dto: TaskListItemDto
): CherryPickContainer {
  const sourceTasks = dto.source_tasks ?? []
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    executionStatus: dto.execution_status ?? dto.status,
    evaluationStatus: dto.evaluation_status ?? 'pending',
    totalCases: dto.total_cases,
    mergeType: dto.is_cherry_pick ? 'picked' : 'whole',
    sourceTaskCount: sourceTasks.length,
    sourceResultCount: dto.total_cases ?? 0,
    sourceTaskIds: sourceTasks.map((t) => t.id),
    sourceTasks: sourceTasks.map((t) => ({
      id: t.id,
      name: t.name,
      resultCount: t.total_cases ?? 0,
      status: t.status ?? '',
    })),
    createdAt: dto.created_at ?? '',
    isFavorite: dto.is_favorite ?? false,
  }
}

/** 日志行（GET /logs?task_id= 行 → TaskLogEntry；time→timestamp、content→message） */
export function toTaskLogEntry(dto: TaskLogEntryDto): TaskLogEntry {
  return {
    id: dto.id,
    timestamp: dto.time ?? '',
    level: (dto.level === 'warn' || dto.level === 'error' ? dto.level : 'info') as TaskLogEntry['level'],
    message: dto.content ?? '',
  }
}

/** 重新执行响应（POST /tasks/{id}/retry → TaskRetryResult，snake_case→camelCase） */
export function toTaskRetryResult(dto: TaskRetryResultDto): TaskRetryResult {
  return { taskId: dto.task_id, status: dto.status }
}

/** 重新评估响应（POST /evaluation/task/reevaluate → TaskReevaluateResult，snake_case→camelCase） */
export function toTaskReevaluateResult(dto: TaskReevaluateResultDto): TaskReevaluateResult {
  return {
    totalCases: dto.total_cases,
    queuedCases: dto.queued_cases,
    reextractedCases: dto.reextracted_cases,
    message: dto.message,
  }
}
