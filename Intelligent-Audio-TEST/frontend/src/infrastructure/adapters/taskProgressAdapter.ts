/**
 * TaskProgress Adapter —— Socket 进度 payload(snake_case DTO) → 前端 ReadModel(camelCase)
 *
 * 后端契约：shared/schemas/socket_payloads.py::TaskProgressPayload（统一 snake_case）。
 * 本文件是 task_progress 通道唯一允许出现 task_id → taskId 键名转换的地方。
 * ReadModel 定义在 domain/model/taskProgress.ts，本文件只做转换。
 */
import type {
  TaskProgressDto,
  TaskProgressHttpDto,
  TaskProgressCurrentCaseDto,
  TaskProgressCaseItemDto,
  ApiResourceStatusDto,
} from '../dto/taskProgressDto'
import type { TaskStatusType } from '../../domain/enums'
import type {
  TaskProgress,
  TaskProgressHttp,
  TaskProgressCurrentCase,
  TaskProgressHttpCurrentCase,
  TaskProgressCaseItem,
  TaskProgressApiResource,
  TaskStartResult,
} from '../../domain/model/taskProgress'
import { toSafeNumber as num } from './commonAdapter'

function toCurrentCase(raw: TaskProgressCurrentCaseDto): TaskProgressCurrentCase {
  return {
    caseId: String(raw.case_id ?? ''),
    name: String(raw.name ?? '未知用例'),
    step: raw.step,
    startTime: num(raw.start_time, Date.now()),
  }
}

function toCaseItem(raw: TaskProgressCaseItemDto): TaskProgressCaseItem {
  return {
    id: String(raw.id ?? ''),
    status: String(raw.status ?? ''),
    executionStatus: String(raw.execution_status ?? ''),
    evaluationStatus: String(raw.evaluation_status ?? ''),
    duration: num(raw.duration),
    errorMessage: String(raw.error_message ?? ''),
    roundProgress: raw.round_progress
      ? { current: num(raw.round_progress.current), total: num(raw.round_progress.total) }
      : undefined,
  }
}

function toApiResource(raw: ApiResourceStatusDto): TaskProgressApiResource {
  return {
    id: String(raw.id ?? ''),
    name: String(raw.name ?? ''),
    currentConcurrent: num(raw.current_concurrent),
    queueLength: num(raw.queue_length),
    avgResponseTime: num(raw.avg_response_time),
    maxConcurrent: num(raw.max_concurrent, 5),
  }
}

// ===== 主转换 =====

export function toTaskProgress(raw: TaskProgressDto): TaskProgress {
  return {
    taskId: String(raw.task_id ?? ''),
    status: (raw.status ?? '') as TaskStatusType,
    totalProgress: num(raw.total_progress),
    completedCount: num(raw.completed_count),
    inProgressCount: num(raw.in_progress_count),
    executionFailedCount: num(raw.execution_failed_count),
    evaluationFailedCount: num(raw.evaluation_failed_count),
    totalCount: num(raw.total_count),
    currentCase: raw.current_case ? toCurrentCase(raw.current_case) : null,
    testCases: (raw.test_cases ?? []).map(toCaseItem),
    logs: (raw.logs ?? []).map(log => ({
      id: num(log.id),
      level: String(log.level ?? 'info'),
      message: String(log.message ?? ''),
      timestamp: num(log.timestamp, Date.now()),
    })),
    apiResources: (raw.api_resources ?? []).map(toApiResource),
    expectedTotalTime: raw.expected_total_time ?? null,
    expectedCompleteTime: raw.expected_complete_time ?? null,
    usedTime: String(raw.used_time ?? '0分钟'),
  }
}

/** 任务启动响应转换（snake_case → camelCase） */
export function toTaskStartResult(raw: Record<string, any>): TaskStartResult {
  return {
    taskId: String(raw.task_id ?? ''),
    status: String(raw.status ?? ''),
    expectedTotalTime: raw.expected_total_time,
    expectedCompleteTime: raw.expected_complete_time,
  }
}

// ===== HTTP 轮询通道 =====

/** HTTP 轮询当前用例转换（started_at 字符串时间） */
function toHttpCurrentCase(raw: NonNullable<TaskProgressHttpDto['current_case']>): TaskProgressHttpCurrentCase {
  return {
    caseId: String(raw.case_id ?? ''),
    name: String(raw.name ?? '未知用例'),
    step: raw.step ?? undefined,
    startedAt: raw.started_at ?? undefined,
  }
}

/** HTTP 轮询进度转换（GET /tasks/{id}/progress → TaskProgressHttp） */
export function toTaskProgressHttp(raw: TaskProgressHttpDto): TaskProgressHttp {
  return {
    taskId: String(raw.task_id ?? ''),
    status: (raw.status ?? '') as TaskStatusType,
    totalCases: num(raw.total_cases),
    completedCases: num(raw.completed_cases),
    failedCases: num(raw.failed_cases),
    progress: num(raw.progress),
    currentCase: raw.current_case ? toHttpCurrentCase(raw.current_case) : null,
    updatedAt: raw.updated_at ?? undefined,
  }
}

/** Socket task_log 事件 payload 转换（snake_case → camelCase） */
export function toTaskLogPayload(raw: Record<string, any>): { taskId: string; log: any } {
  const log = raw.log ?? {}
  return {
    taskId: String(raw.task_id ?? ''),
    log: {
      ...log,
      testCaseId: log.testCaseId ?? String(log.test_case_id ?? ''),
    },
  }
}

/** Socket subscribe_task / unsubscribe_task emit 体转换（camelCase → snake_case） */
export function toTaskSubscriptionDto(taskId: string | number): { task_id: string } {
  return { task_id: String(taskId) }
}
