/**
 * Task Adapter —— TaskDto(snake_case) ⇄ Task(camelCase)
 *
 * 唯一允许出现 task_id → taskId 这类键名转换的地方。
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 */
import type {
  Task,
  TaskCreateDraft,
  TaskDeviceBrief,
  TaskApiBrief,
  TaskCaseBrief,
  TaskSourceBrief,
  TaskDomainStats,
  TaskCaseRemoveResult,
  TaskContainerStats,
} from '../../domain/model/task'
import type {
  CaseDetail,
  CaseResults,
  CaseExecutionResult,
  CaseDimensionResult,
  CaseResultAudio,
  ReviewHistoryItem,
} from '../../domain/model/taskCaseDetail'
import type { TaskStatusType } from '../../domain/enums'
import type { ReportMetricConfig } from '../../domain/model/report'
import type { TaskDto, TaskDetailDto, TaskCaseBriefDto, TaskCreateDto, TaskSourceBriefDto, TaskDomainStatsDto, TaskContainerStatsDto, TaskCaseDeviceAssignmentDto } from '../dto/taskDto'
import { s } from './report.utils'
import { toSafeNumber as n } from './commonAdapter'
import { toAlgorithmResultItem, toReferenceParamsDict, toFieldMappingItem } from './report.mapping'

// ===== DTO → Domain =====

function toDeviceBrief(raw: TaskDto['devices'][number]): TaskDeviceBrief {
  return { id: raw.id, name: raw.name, status: raw.status ?? undefined, model: raw.model ?? undefined }
}

function toApiBrief(raw: TaskDto['apis'][number]): TaskApiBrief {
  return { id: raw.id, name: raw.name, status: raw.status ?? undefined }
}

function toSourceBrief(raw: TaskSourceBriefDto): TaskSourceBrief {
  return {
    id: raw.id,
    name: raw.name,
    status: raw.status ?? undefined,
    totalCases: raw.total_cases ?? undefined,
    completedCases: raw.completed_cases ?? undefined,
    failedCases: raw.failed_cases ?? undefined,
    createdAt: raw.created_at ?? undefined,
  }
}

/** 任务详情关联用例简报 → TaskCaseBrief（Domain） */
export function toTaskCaseBrief(raw: TaskCaseBriefDto): TaskCaseBrief {
  return {
    caseId: raw.case_id,
    name: raw.name,
    status: raw.status ?? undefined,
    executionStatus: raw.execution_status ?? undefined,
    evaluationStatus: raw.evaluation_status ?? undefined,
    startedAt: raw.started_at ?? undefined,
    completedAt: raw.completed_at ?? undefined,
    duration: raw.duration ?? undefined,
    errorMessage: raw.error_message ?? undefined,
    groupName: raw.group_name ?? undefined,
    tags: raw.tags ?? [],
    // INT-302/F3：本任务用例聚合的评估维度（snake_case → camelCase）
    evaluationDimensions: (raw.evaluation_dimensions ?? [])
      .filter((d): d is { id: number | string; name?: string | null } =>
        !!d && d.id !== undefined && d.id !== null)
      .map(d => ({ id: Number(d.id), name: d.name ?? String(d.id) })),
    // INT-340：该用例下是否存在人工复核结果
    reviewed: raw.reviewed ?? false,
  }
}

/** 任务 DTO → Task（列表项/详情通用；cases 仅详情有） */
export function toTask(dto: TaskDto | TaskDetailDto): Task {
  const d = dto as TaskDetailDto
  return {
    id: d.id,
    name: d.name,
    description: d.description ?? undefined,
    deviceTypes: d.device_types ?? [],
    status: d.status as TaskStatusType,
    // INT-301：任务级执行/评估双状态（评估推进只落评估侧）
    executionStatus: d.execution_status ?? undefined,
    evaluationStatus: d.evaluation_status ?? undefined,
    progress: d.progress ?? undefined,
    config: d.config,
    algorithmType: d.algorithm_type ?? undefined,
    algorithmParams: d.algorithm_params ?? undefined,
    startedAt: d.started_at ?? undefined,
    completedAt: d.completed_at ?? undefined,
    expectedTotalTime: d.expected_total_time ?? undefined,
    expectedCompleteTime: d.expected_complete_time ?? undefined,
    usedTime: d.used_time ?? undefined,
    totalCases: d.total_cases ?? undefined,
    caseCount: d.case_count ?? undefined,
    deviceCount: d.device_count ?? undefined,
    completedCases: d.completed_cases ?? undefined,
    failedCases: d.failed_cases ?? undefined,
    // INT-340：任务下已复核结果条数（覆盖提醒 + 报告页「人工复核」标记）
    reviewCount: d.review_count ?? 0,
    tags: d.tags ?? [],
    createdAt: d.created_at ?? undefined,
    updatedAt: d.updated_at ?? undefined,
    finishedAt: d.finished_at ?? undefined,
    error: d.error ?? undefined,
    deleted: d.deleted,
    deletedAt: d.deleted_at ?? undefined,
    deletedByUserId: d.deleted_by_user_id ?? undefined,
    // INT-339：挑选合并容器标记
    isCherryPick: d.is_cherry_pick,
    // INT-423/467：可见性 + 归属人（两端同名，显式映射；缺省回落 undefined）
    visibility: d.visibility ?? undefined,
    createdByUserId: d.created_by_user_id ?? undefined,
    // INT-577：统一合并容器「合并方式」+ 来源任务/结果计数（列表次行「来源 {n} 任务 · 结果 {m} 条」）
    mergeType: d.merge_type ?? null,
    sourceTaskCount: d.source_task_count ?? null,
    sourceResultCount: d.source_result_count ?? null,
    result: d.result,
    reports: d.reports
      ? {
          count: d.reports.count,
          reports: (d.reports.reports ?? []).map(r => ({
            id: r.id,
            name: r.name,
            status: r.status,
            type: r.type,
            createdAt: r.created_at,
          })),
        }
      : undefined,
    devices: (d.devices ?? []).map(toDeviceBrief),
    apis: (d.apis ?? []).map(toApiBrief),
    sourceTasks: (d.source_tasks ?? []).map(toSourceBrief),
    cases: Array.isArray(d.cases) ? d.cases.map(toTaskCaseBrief) : undefined,
  }
}

export function toTaskList(dtos: (TaskDto | TaskDetailDto)[] | null | undefined): Task[] {
  return (dtos ?? []).map(toTask)
}

/** INT-577：合并容器统计 DTO → Domain（缺省 0；供「挑选合并」页签计数/facet 徽章） */
export function toContainerStats(dto: TaskContainerStatsDto | null | undefined): TaskContainerStats | null {
  if (!dto || typeof dto.total !== 'number') return null
  return {
    total: dto.total ?? 0,
    whole: dto.whole ?? 0,
    picked: dto.picked ?? 0,
  }
}

/** 用例移除响应 DTO → TaskCaseRemoveResult（INT-305；snake_case → camelCase） */
export function toTaskCaseRemoveResult(raw: Record<string, unknown>): TaskCaseRemoveResult {
  return {
    taskId: String(raw.taskId ?? raw.task_id ?? ''),
    caseId: String(raw.caseId ?? raw.case_id ?? ''),
    removed: Boolean(raw.removed ?? true),
    idempotent: Boolean(raw.idempotent ?? false),
    purged: Boolean(raw.purged ?? false),
    reportRequeued: Boolean(raw.reportRequeued ?? raw.report_requeued ?? false),
  }
}

/** 任务域全量聚合统计 DTO → TaskDomainStats（INT-200） */
export function toTaskDomainStats(dto: TaskDomainStatsDto | null | undefined): TaskDomainStats {
  const typeCounts = dto?.type_counts ?? { api: 0, e2e: 0, mixed: 0 }
  return {
    total: n(dto?.total),
    deletedTotal: n(dto?.deleted_total),
    statusCounts: dto?.status_counts ?? {},
    typeCounts: {
      api: n(typeCounts.api),
      e2e: n(typeCounts.e2e),
      mixed: n(typeCounts.mixed),
    },
    trend: (dto?.trend ?? []).map(b => ({ key: b.key, count: n(b.count) })),
    granularity: dto?.granularity ?? 'day',
  }
}

// ===== Domain → DTO（请求体） =====

/** 任务创建草稿 → TaskCreateRequest 请求体 */
export function toTaskCreateDto(draft: TaskCreateDraft): TaskCreateDto {
  return {
    name: draft.name,
    description: draft.description,
    // INT-282：执行口径显式透传（后端 task.type 已废弃会忽略，契约兼容留痕）
    type: draft.type,
    config: draft.config,
    case_ids: draft.caseIds,
    device_ids: draft.deviceIds,
    api_ids: draft.apiIds,
    // INT-1434：用例级被测设备选择（caseId/deviceType/deviceId/labId → snake_case 契约）
    case_devices: draft.caseDevices?.map(a => ({
      case_id: a.caseId,
      device_type: a.deviceType,
      device_id: a.deviceId,
      lab_id: a.labId,
    })),
    // INT-604：任务执行模式 / 串行优先侧（显式透传；后端缺省 parallel/device）
    execution_mode: draft.executionMode,
    serial_first: draft.serialFirst,
    tags: draft.tags,
    algorithm_type: draft.algorithmType,
    algorithm_params: draft.algorithmParams,
    // INT-423/467：新建可见性（缺省不发，后端回落 shared）
    visibility: draft.visibility,
  }
}

// ===== 用例详情 ReadModel（getCaseDetail / getCaseResults / searchCases 复用）=====

/** 维度评估结果（results[].dimensions 元素 → camelCase） */
function toDimensionResult(raw: Record<string, unknown>): CaseDimensionResult {
  return {
    id: raw.id !== undefined ? (raw.id as string | number) : undefined,
    name: raw.name !== undefined ? s(raw.name) : undefined,
    value: raw.value !== undefined && (typeof raw.value === 'string' || typeof raw.value === 'number')
      ? raw.value
      : undefined,
    score: raw.score !== undefined ? n(raw.score) : undefined,
    roundNumber: raw.round_number !== undefined ? n(raw.round_number) : null,
  }
}

/** 复核留痕行（results[].review_history[] 元素 → camelCase） */
function toReviewHistoryItem(raw: Record<string, unknown>): ReviewHistoryItem {
  return {
    id: raw.id !== undefined && raw.id !== null ? Number(raw.id) : undefined,
    resultId: raw.result_id !== undefined && raw.result_id !== null ? Number(raw.result_id) : undefined,
    // INT-796 §3.4：历史抽屉溯源字段（任务/用例/操作人）
    taskId: raw.task_id !== undefined && raw.task_id !== null ? Number(raw.task_id) : undefined,
    testCaseId: raw.test_case_id !== undefined && raw.test_case_id !== null ? String(raw.test_case_id) : undefined,
    fieldName: raw.field_name !== undefined && raw.field_name !== null ? String(raw.field_name) : undefined,
    oldValue: raw.old_value === null || raw.old_value === undefined ? null : String(raw.old_value),
    newValue: raw.new_value === null || raw.new_value === undefined ? null : String(raw.new_value),
    comment: raw.comment === null || raw.comment === undefined ? null : String(raw.comment),
    createdByUserId: raw.created_by_user_id === null || raw.created_by_user_id === undefined
      ? null
      : Number(raw.created_by_user_id),
    createdAt: raw.created_at === null || raw.created_at === undefined ? null : s(raw.created_at),
  }
}

/** 设备/API 执行结果（getCaseResults results[] 元素 → camelCase） */
function toExecutionResult(raw: Record<string, unknown>): CaseExecutionResult {
  return {
    id: raw.id as string | number,
    deviceId: raw.device_id !== undefined ? (raw.device_id as string | number) : undefined,
    deviceName: raw.device_name !== undefined ? s(raw.device_name) : undefined,
    apiId: raw.api_id !== undefined ? (raw.api_id as string | number) : undefined,
    apiName: raw.api_name !== undefined ? s(raw.api_name) : undefined,
    executionStatus: raw.execution_status !== undefined ? s(raw.execution_status) : undefined,
    responseTime: raw.response_time === null || raw.response_time === undefined
      ? undefined
      : n(raw.response_time),
    algorithmResult: raw.algorithm_result !== undefined ? raw.algorithm_result : undefined,
    asrResult: raw.asr_result === null || raw.asr_result === undefined ? null : s(raw.asr_result),
    translationResult: raw.translation_result === null || raw.translation_result === undefined
      ? null
      : s(raw.translation_result),
    resultData: raw.result_data !== undefined ? raw.result_data : undefined,
    errorMessage: raw.error_message === null || raw.error_message === undefined ? null : s(raw.error_message),
    dimensions: Array.isArray(raw.dimensions)
      ? (raw.dimensions as Array<Record<string, unknown>>).map(toDimensionResult)
      : undefined,
    createdAt: raw.created_at === null || raw.created_at === undefined ? null : s(raw.created_at),
    // INT-340：人工复核标记/最近动作/留痕历史（用例结果行「已复核」徽标 + 复核弹窗历史展示）
    reviewed: raw.reviewed !== undefined ? Boolean(raw.reviewed) : undefined,
    reviewedByUserId: raw.reviewed_by_user_id === null || raw.reviewed_by_user_id === undefined
      ? null
      : (raw.reviewed_by_user_id as string | number),
    reviewedAt: raw.reviewed_at === null || raw.reviewed_at === undefined ? null : s(raw.reviewed_at),
    lastReviewComment: raw.last_review_comment === null || raw.last_review_comment === undefined
      ? null
      : s(raw.last_review_comment),
    lastReviewAction: raw.last_review_action === null || raw.last_review_action === undefined
      ? null
      : s(raw.last_review_action),
    reviewHistory: Array.isArray(raw.review_history)
      ? (raw.review_history as Array<Record<string, unknown>>).map(toReviewHistoryItem)
      : undefined,
  }
}

/** 结果音频条目（result_audios 字典值数组元素 → camelCase） */
function toResultAudio(raw: Record<string, unknown>): CaseResultAudio {
  return {
    url: raw.url !== undefined ? s(raw.url) : undefined,
    filename: raw.filename !== undefined ? s(raw.filename) : undefined,
    paramCode: raw.param_code !== undefined ? s(raw.param_code) : undefined,
  }
}

/** 结果音频字典：设备名 → 音频条目数组 → camelCase（字典键为设备名数据 key，保留原样） */
function toResultAudiosDict(raw: unknown): Record<string, CaseResultAudio[]> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const result: Record<string, CaseResultAudio[]> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    result[key] = Array.isArray(value)
      ? (value as Array<Record<string, unknown>>).map(toResultAudio)
      : []
  }
  return result
}

/** 指标配置（metric_configs[] 元素 → ReportMetricConfig；name 必填，code 与 name 恒等时丢弃） */
function toMetricConfig(raw: Record<string, unknown>): ReportMetricConfig {
  return { name: s(raw.name ?? raw.code) }
}

/** 用例详情 DTO → CaseDetail（camelCase ReadModel） */
export function toCaseDetail(raw: Record<string, unknown>): CaseDetail {
  const fieldMapping = (raw.field_mapping as Record<string, unknown> | undefined) ?? {}
  return {
    taskId: s(raw.task_id),
    caseId: s(raw.case_id),
    caseName: s(raw.case_name),
    status: raw.status !== undefined ? s(raw.status) : undefined,
    executionStatus: raw.execution_status !== undefined ? s(raw.execution_status) : undefined,
    evaluationStatus: raw.evaluation_status !== undefined ? s(raw.evaluation_status) : undefined,
    startedAt: raw.started_at === null || raw.started_at === undefined ? null : s(raw.started_at),
    completedAt: raw.completed_at === null || raw.completed_at === undefined ? null : s(raw.completed_at),
    duration: raw.duration === null || raw.duration === undefined ? null : n(raw.duration),
    errorMessage: raw.error_message === null || raw.error_message === undefined ? null : s(raw.error_message),
    audioList: Array.isArray(raw.audio_list) ? raw.audio_list : [],
    referenceParams: toReferenceParamsDict(raw.reference_params),
    algorithmResults: Array.isArray(raw.algorithm_results)
      ? (raw.algorithm_results as Array<Record<string, unknown>>).map(toAlgorithmResultItem)
      : [],
    algorithmType: s(raw.algorithm_type),
    devices: Array.isArray(raw.devices) ? (raw.devices as unknown[]).map(v => s(v)) : [],
    metricConfigs: Array.isArray(raw.metric_configs)
      ? (raw.metric_configs as Array<Record<string, unknown>>).map(toMetricConfig)
      : [],
    fieldMapping: {
      result: Array.isArray(fieldMapping.result)
        ? (fieldMapping.result as Array<Record<string, unknown>>).map(toFieldMappingItem)
        : [],
      reference: Array.isArray(fieldMapping.reference)
        ? (fieldMapping.reference as Array<Record<string, unknown>>).map(toFieldMappingItem)
        : [],
    },
    resultAudios: toResultAudiosDict(raw.result_audios),
  }
}

/** 用例结果集 DTO → CaseResults（camelCase ReadModel） */
export function toCaseResults(raw: Record<string, unknown>): CaseResults {
  return {
    taskId: raw.task_id !== undefined ? s(raw.task_id) : undefined,
    caseId: raw.case_id !== undefined ? s(raw.case_id) : undefined,
    caseName: raw.case_name !== undefined ? s(raw.case_name) : undefined,
    results: Array.isArray(raw.results)
      ? (raw.results as Array<Record<string, unknown>>).map(toExecutionResult)
      : [],
  }
}
