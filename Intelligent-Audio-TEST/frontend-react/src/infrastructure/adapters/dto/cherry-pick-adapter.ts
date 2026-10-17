/**
 * 挑选合并 DTO→Domain 转换器（infrastructure/adapters/dto，18_挑选合并交互重设计.md §7.3）。
 * snake_case 唯一出现层；前端只见 camelCase Domain。
 * 对照契约：cherry_pick_bp.py:22-91 + cherry_pick_service.py（mock 响应同形）。
 */
import type {
  CherryPickCandidate,
  CherryPickContainer,
  PickCartEntry,
  PickCartGroup,
  PickPreview,
  PickSet,
} from '@/domain/models/cherryPick'
import type {
  CherryPickCandidateDto,
  CherryPickContainerDto,
  PickCartEntryDto,
  PickCartGroupDto,
  PickPreviewDto,
  PickSetDto,
} from '@/infrastructure/mock/cherry-pick-mock'

export function fromCandidateDto(dto: CherryPickCandidateDto): CherryPickCandidate {
  return {
    resultId: dto.result_id,
    taskId: dto.task_id,
    taskName: dto.task_name,
    caseId: dto.case_id,
    caseName: dto.case_name,
    deviceId: dto.device_id,
    deviceName: dto.device_name,
    apiId: dto.api_id,
    apiName: dto.api_name,
    resultType: dto.result_type || 'default',
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    evaluated: dto.evaluated,
    createdAt: dto.created_at,
  }
}

export function fromCartEntryDto(dto: PickCartEntryDto): PickCartEntry {
  return {
    itemId: dto.item_id,
    resultId: dto.result_id,
    sourceTaskId: dto.source_task_id,
    sourceTaskName: dto.source_task_name,
    sourceCaseId: dto.source_case_id,
    sourceCaseName: dto.source_case_name,
    sourceDeviceId: dto.source_device_id,
    sourceDeviceName: dto.source_device_name,
    sourceApiId: dto.source_api_id,
    sourceApiName: dto.source_api_name,
    sourceResultType: dto.source_result_type,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    invalid: dto.invalid,
  }
}

export function fromCartGroupDto(dto: PickCartGroupDto): PickCartGroup {
  return {
    taskId: dto.task_id,
    taskName: dto.task_name,
    entries: dto.entries.map(fromCartEntryDto),
  }
}

export function fromPickSetDto(dto: PickSetDto): PickSet {
  return {
    setId: dto.set_id,
    name: dto.name,
    createdAt: dto.created_at,
    itemCount: dto.item_count,
    entries: dto.entries.map(fromCartEntryDto),
  }
}

export function fromPreviewDto(dto: PickPreviewDto): PickPreview {
  return {
    totalResults: dto.total_results,
    invalidResultIds: dto.invalid_result_ids,
    sourceTaskCount: dto.source_task_count,
    deviceIds: dto.device_ids,
    caseCount: dto.case_count,
    executionStatusCounts: dto.execution_status_counts,
    duplicates: dto.duplicates,
    configInconsistent: dto.config_inconsistent,
    configFields: dto.config_fields,
    sourceConfigs: dto.source_configs,
  }
}

export function fromContainerDto(dto: CherryPickContainerDto): CherryPickContainer {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    totalCases: dto.total_cases,
    mergeType: dto.merge_type,
    sourceTaskCount: dto.source_task_count,
    sourceResultCount: dto.source_result_count,
    sourceTaskIds: dto.source_task_ids,
    sourceTasks: dto.source_tasks.map((t) => ({
      id: t.id,
      name: t.name,
      resultCount: t.result_count,
      status: t.status,
    })),
    createdAt: dto.created_at,
    isFavorite: dto.is_favorite,
  }
}
