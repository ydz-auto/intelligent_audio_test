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
} from '../../domain/model/task'
import type {
  CaseDetail,
  CaseResults,
  CaseExecutionResult,
  CaseDimensionResult,
  CaseResultAudio,
} from '../../domain/model/taskCaseDetail'
import type { TaskStatusType, TaskType } from '../../domain/enums'
import type { ReportMetricConfig } from '../../domain/model/report'
import type { TaskDto, TaskDetailDto, TaskCaseBriefDto, TaskCreateDto } from '../dto/taskDto'
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
  }
}

/** 任务 DTO → Task（列表项/详情通用；cases 仅详情有） */
export function toTask(dto: TaskDto | TaskDetailDto): Task {
  const d = dto as TaskDetailDto
  return {
    id: d.id,
    name: d.name,
    description: d.description ?? undefined,
    type: d.type as TaskType,
    status: d.status as TaskStatusType,
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
    tags: d.tags ?? [],
    createdAt: d.created_at ?? undefined,
    updatedAt: d.updated_at ?? undefined,
    finishedAt: d.finished_at ?? undefined,
    error: d.error ?? undefined,
    deleted: d.deleted,
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
    cases: Array.isArray(d.cases) ? d.cases.map(toTaskCaseBrief) : undefined,
  }
}

export function toTaskList(dtos: (TaskDto | TaskDetailDto)[] | null | undefined): Task[] {
  return (dtos ?? []).map(toTask)
}

// ===== Domain → DTO（请求体） =====

/** 任务创建草稿 → TaskCreateRequest 请求体 */
export function toTaskCreateDto(draft: TaskCreateDraft): TaskCreateDto {
  return {
    name: draft.name,
    type: draft.type,
    description: draft.description,
    config: draft.config,
    case_ids: draft.caseIds,
    device_ids: draft.deviceIds,
    api_ids: draft.apiIds,
    tags: draft.tags,
    algorithm_type: draft.algorithmType,
    algorithm_params: draft.algorithmParams,
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
