/**
 * 任务域 DTO→Domain 转换器（infrastructure/adapters/dto，09_任务域.md §10）。
 * 本层是任务域 snake_case 后端契约唯一转成 camelCase 领域对象的地方（架构红线：
 * 前端只见 camelCase 领域对象）；同时补派生字段：apiCount（apis.length）、
 * sourceTaskCount/sourceTaskIds（合并/挑选容器）、concurrency（config.concurrent_tasks，
 * 后端真实字段）。日志行（TaskLogEntryDto）为字段改名映射（time→timestamp、content→message）。
 */
import type { CherryPickContainer } from '@/domain/models/cherryPick'
import type {
  CherryPickTask,
  MergeType,
  PublishedTaskDetail,
  PublishedTaskExecuteResult,
  PublishedTaskExecutionItem,
  PublishedTaskItem,
  TaskCaseBrief,
  TaskCaseTarget,
  TaskDetailData,
  TaskListItem,
  TaskLogEntry,
  TaskReevaluateResult,
  TaskReportItem,
  TaskRetryResult,
  TaskSourceBrief,
} from '@/domain/models/task'
import type {
  PaginatedDto,
  PublishedTaskDetailDto,
  PublishedTaskExecuteResultDto,
  PublishedTaskExecutionDto,
  PublishedTaskItemDto,
  TaskCaseBriefDto,
  TaskCaseTargetDto,
  TaskDetailDto,
  TaskListItemDto,
  TaskLogEntryDto,
  TaskReevaluateResultDto,
  TaskReportItemDto,
  TaskRetryResultDto,
  TaskSourceBriefDto,
} from '@/infrastructure/dto/task.dto'

/**
 * 合并方式归一（INT-577）：后端 merge_type 为准；旧版本仅返 is_cherry_pick 时
 * 按 picked 兜底（该字段本身即结果挑选容器判定）。
 */
function toMergeType(dto: TaskListItemDto): MergeType | null {
  if (dto.merge_type === 'whole' || dto.merge_type === 'picked') return dto.merge_type
  return dto.is_cherry_pick ? 'picked' : null
}

function toTaskReportItem(dto: TaskReportItemDto): TaskReportItem {
  return {
    id: dto.id,
    name: dto.name,
    status: dto.status,
    type: dto.type,
    createdAt: dto.created_at,
  }
}

function toTaskSourceBrief(dto: TaskSourceBriefDto): TaskSourceBrief {
  return {
    id: dto.id,
    name: dto.name,
    status: dto.status,
    totalCases: dto.total_cases,
    completedCases: dto.completed_cases,
    failedCases: dto.failed_cases,
    createdAt: dto.created_at,
  }
}

function toTaskCaseTarget(dto: TaskCaseTargetDto): TaskCaseTarget {
  return {
    taskCaseId: dto.task_case_id,
    targetType: dto.target_type ?? null,
    deviceType: dto.device_type ?? null,
    deviceId: dto.device_id ?? null,
    apiId: dto.api_id ?? null,
    targetName: dto.target_name ?? null,
    status: dto.status,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    duration: dto.duration,
    errorMessage: dto.error_message,
  }
}

function toTaskCaseBrief(dto: TaskCaseBriefDto): TaskCaseBrief {
  return {
    caseId: dto.case_id,
    name: dto.name,
    status: dto.status,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    duration: dto.duration,
    roundsCount: dto.rounds_count ?? null,
    errorMessage: dto.error_message,
    groupName: dto.group_name,
    tags: dto.tags ?? [],
    evaluationDimensions: dto.evaluation_dimensions ?? [],
    reviewed: dto.reviewed ?? false,
    targetCount: dto.target_count ?? null,
    targets: (dto.targets ?? []).map(toTaskCaseTarget),
  }
}

/** TaskListItem：后端 snake_case 字段逐一映射 + apiCount 派生 */
export function toTaskListItem(dto: TaskListItemDto): TaskListItem {
  const isCherryPick = dto.is_cherry_pick ?? false
  const sourceTasks = dto.source_tasks ?? []
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    status: dto.status,
    executionStatus: dto.execution_status as TaskListItem['executionStatus'],
    evaluationStatus: dto.evaluation_status as TaskListItem['evaluationStatus'],
    deviceTypes: dto.device_types ?? [],
    config: dto.config ?? {},
    algorithmType: dto.algorithm_type,
    algorithmParams: dto.algorithm_params,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    totalCases: dto.total_cases,
    caseCount: dto.case_count ?? dto.total_cases,
    deviceCount: dto.device_count,
    completedCases: dto.completed_cases,
    failedCases: dto.failed_cases,
    apiCount: (dto.apis ?? []).length,
    tags: dto.tags ?? [],
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    isFavorite: dto.is_favorite,
    isCherryPick,
    mergeType: toMergeType(dto),
    sourceTaskCount: dto.source_task_count ?? (sourceTasks.length || null),
    sourceResultCount: dto.source_result_count ?? null,
    deleted: dto.deleted,
    deletedAt: dto.deleted_at,
    deletedByUserId: dto.deleted_by_user_id,
    reports: dto.reports
      ? {
          count: dto.reports.count,
          reports: (dto.reports.reports ?? []).map(toTaskReportItem),
        }
      : null,
    devices: dto.devices ?? [],
    apis: dto.apis ?? [],
    sourceTasks: sourceTasks.map(toTaskSourceBrief),
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

/** TaskDetail：后端 snake_case 字段逐一映射 + apiCount/concurrency 派生 */
export function toTaskDetail(dto: TaskDetailDto): TaskDetailData {
  const config = dto.config ?? {}
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    status: dto.status,
    executionStatus: dto.execution_status as TaskDetailData['executionStatus'],
    evaluationStatus: dto.evaluation_status as TaskDetailData['evaluationStatus'],
    deviceTypes: dto.device_types ?? [],
    config,
    algorithmType: dto.algorithm_type,
    algorithmParams: dto.algorithm_params,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    expectedTotalTime: dto.expected_total_time,
    expectedCompleteTime: dto.expected_complete_time,
    usedTime: dto.used_time,
    totalCases: dto.total_cases,
    caseCount: dto.case_count ?? dto.total_cases,
    deviceCount: dto.device_count,
    completedCases: dto.completed_cases,
    failedCases: dto.failed_cases,
    apiCount: (dto.apis ?? []).length,
    concurrency:
      typeof config.concurrent_tasks === 'number' ? config.concurrent_tasks : null,
    tags: dto.tags ?? [],
    cases: (dto.cases ?? []).map(toTaskCaseBrief),
    devices: dto.devices ?? [],
    apis: dto.apis ?? [],
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    reviewCount: dto.review_count ?? 0,
    // INT-2446：创建人 id 原样映射（姓名字段后端未提供，由 application 层查用户详情）
    createdByUserId: dto.created_by_user_id ?? null,
  }
}

/** 已发布任务列表项（published_task.py PublishedTaskItem → camelCase 领域对象） */
export function toPublishedTaskItem(dto: PublishedTaskItemDto): PublishedTaskItem {
  return {
    id: dto.id,
    sourceTaskId: dto.source_task_id,
    name: dto.name,
    description: dto.description,
    type: dto.type,
    algorithmType: dto.algorithm_type,
    status: dto.status,
    benchmark: dto.benchmark,
    version: dto.version,
    isCurrent: dto.is_current,
    versionCount: dto.version_count,
    publishedBy: dto.published_by,
    publishedAt: dto.published_at,
    archivedAt: dto.archived_at,
    createdAt: dto.created_at,
  }
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

/** 已发布任务执行记录（published_task.py PublishedTaskExecutionItem） */
function toPublishedTaskExecutionItem(
  dto: PublishedTaskExecutionDto
): PublishedTaskExecutionItem {
  return {
    taskId: dto.task_id,
    taskName: dto.task_name,
    version: dto.version,
    status: dto.status,
    totalCases: dto.total_cases,
    completedCases: dto.completed_cases,
    createdAt: dto.created_at,
    completedAt: dto.completed_at,
  }
}

/** 已发布任务详情（GET /published-tasks/{id} → PublishedTaskDetail） */
export function toPublishedTaskDetail(dto: PublishedTaskDetailDto): PublishedTaskDetail {
  return {
    id: dto.id,
    taskGroupId: dto.task_group_id,
    sourceTaskId: dto.source_task_id,
    name: dto.name,
    description: dto.description,
    status: dto.status,
    benchmark: dto.benchmark,
    version: dto.version,
    isCurrent: dto.is_current,
    snapshotConfig: dto.snapshot_config,
    hasTaskSnapshot: dto.has_task_snapshot,
    publishReason: dto.publish_reason,
    publishedBy: dto.published_by,
    publishedAt: dto.published_at,
    archivedBy: dto.archived_by,
    archivedAt: dto.archived_at,
    sourceTaskName: dto.source_task_name,
    sourceTaskStatus: dto.source_task_status,
    sourceTaskTotalCases: dto.source_task_total_cases,
    sourceTaskCompletedCases: dto.source_task_completed_cases,
    reportSnapshot: dto.report_snapshot,
    hasReportSnapshot: dto.has_report_snapshot,
    versions: (dto.versions ?? []).map(toPublishedTaskItem),
    executionHistory: (dto.execution_history ?? []).map(toPublishedTaskExecutionItem),
  }
}

/** 已发布任务执行结果（POST execute → PublishedTaskExecuteResult） */
export function toPublishedTaskExecuteResult(
  dto: PublishedTaskExecuteResultDto
): PublishedTaskExecuteResult {
  return {
    taskId: dto.task_id,
    taskName: dto.task_name,
    publishedTaskId: dto.published_task_id,
    publishedTaskVersion: dto.published_task_version,
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
    executionStatus: (dto.execution_status ?? 'pending') as CherryPickTask['executionStatus'],
    evaluationStatus: (dto.evaluation_status ??
      'pending') as CherryPickTask['evaluationStatus'],
    totalCases: dto.total_cases,
    sourceTaskCount: sourceTasks.length,
    sourceTaskIds: sourceTasks.map((t) => t.id),
    createdAt: dto.created_at,
    isFavorite: dto.is_favorite,
  }
}

/**
 * 统一合并容器（GET /tasks?merged=true ∪ ?cherry_pick=true 双查询行 → CherryPickContainer，
 * §11-1 落地前客户端双查询合并）。mergeType 派生：is_cherry_pick=true → picked，
 * 否则（status=merged）→ whole；sourceResultCount 后端列表行未返，以 total_cases 近似。
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
    // §5.5.4 列表「部分失败」映射：case_count 优先（= 容器用例数），缺省退回 total_cases
    caseCount: dto.case_count ?? dto.total_cases ?? null,
    failedCases: dto.failed_cases ?? null,
    mergeType: dto.is_cherry_pick ? 'picked' : 'whole',
    sourceTaskCount: dto.source_task_count ?? sourceTasks.length,
    // 后端容器计数优先：source_tasks[].total_cases 是源任务用例数，不等于挑选结果条数
    sourceResultCount: dto.source_result_count ?? dto.total_cases ?? 0,
    sourceTaskIds: sourceTasks.map((t) => t.id),
    sourceTasks: sourceTasks.map((t) => ({
      id: t.id,
      name: t.name,
      resultCount: t.total_cases ?? 0,
      status: t.status ?? '',
    })),
    createdAt: dto.created_at ?? '',
    isFavorite: dto.is_favorite ?? false,
    reports: dto.reports,
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

/** 重新执行响应（POST /tasks/{id}/retry → TaskRetryResult） */
export function toTaskRetryResult(dto: TaskRetryResultDto): TaskRetryResult {
  return { taskId: dto.task_id, status: dto.status }
}

/** 重新评估响应（POST /evaluation/task/reevaluate → TaskReevaluateResult） */
export function toTaskReevaluateResult(dto: TaskReevaluateResultDto): TaskReevaluateResult {
  return {
    totalCases: dto.total_cases,
    queuedCases: dto.queued_cases,
    reextractedCases: dto.reextracted_cases,
    message: dto.message,
  }
}
