/**
 * 挑选合并 DTO→Domain 转换器（infrastructure/adapters/dto，18_挑选合并交互重设计.md §7.3）。
 * snake_case 唯一出现层；前端只见 camelCase Domain。
 * 对照契约：cherry_pick_bp.py + task_service cherry_pick_service.py（真实接口响应形态）。
 * 后端候选/购物车响应缺展示名与结果类型字段（§11-2/§11-5 未补前）——
 * 缺名按「用例 ID / 设备 ID / 结果类型待补充」降级，见 domain/lib/cherry-pick-tree.ts。
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
} from '@/infrastructure/dto/cherry-pick.dto'

export function fromCandidateDto(dto: CherryPickCandidateDto): CherryPickCandidate {
  return {
    resultId: dto.result_id,
    taskId: dto.task_id,
    taskName: dto.task_name,
    caseId: dto.case_id,
    // §11-2 未补前缺 case_name → 界面降级显示用例 ID
    caseName: dto.case_id,
    deviceId: dto.device_id,
    deviceName: null,
    apiId: dto.api_id,
    apiName: null,
    // 结果类型后端候选行未返（缺省 default，挑选树按缺省合并）
    resultType: 'default',
    executionStatus: dto.execution_status,
    // 候选行无独立 evaluation_status 字段：已评估（evaluated=true）→ completed，否则 pending
    evaluationStatus: dto.evaluated ? 'completed' : 'pending',
    evaluated: dto.evaluated,
    createdAt: dto.created_at ?? '',
  }
}

export function fromCartEntryDto(dto: PickCartEntryDto): PickCartEntry {
  return {
    // 后端购物车条目 ID 为整型（CherryPickCartItem.id）；Domain 以字符串作 React key / 批量移除标识
    itemId: String(dto.item_id),
    resultId: dto.result_id,
    sourceTaskId: dto.source_task_id,
    sourceTaskName: dto.source_task_name,
    sourceCaseId: dto.source_case_id,
    // §11-5 未补前缺 case/device/api 名称字段 → 界面降级显示 ID
    sourceCaseName: dto.source_case_id,
    sourceDeviceId: dto.source_device_id,
    sourceDeviceName: null,
    sourceApiId: dto.source_api_id,
    sourceApiName: null,
    sourceResultType: null,
    executionStatus: dto.execution_status,
    // 购物车条目后端未返评估状态 → 置空（界面不渲染该列）
    evaluationStatus: null,
    invalid: dto.invalid,
  }
}

export function fromCartGroupDto(dto: PickCartGroupDto): PickCartGroup {
  return {
    taskId: dto.source_task_id,
    taskName: dto.source_task_name,
    entries: (dto.items ?? []).map(fromCartEntryDto),
  }
}

export function fromPickSetDto(dto: PickSetDto): PickSet {
  return {
    setId: String(dto.set_id),
    name: dto.name,
    createdAt: dto.created_at ?? '',
    itemCount: dto.item_count,
    // sets_list 响应为摘要（含 item_count），不含条目明细；恢复/删除走 setId
    entries: [],
  }
}

export function fromPreviewDto(dto: PickPreviewDto): PickPreview {
  return {
    totalResults: dto.total_results,
    invalidResultIds: dto.invalid_result_ids ?? [],
    sourceTaskCount: dto.source_task_count,
    deviceIds: dto.device_ids ?? [],
    caseCount: dto.case_count,
    executionStatusCounts: dto.execution_status_counts ?? {},
    // 后端 duplicates 为 [{device_id, case_id, count}] 明细；Domain 仅消费组数
    duplicates: (dto.duplicates ?? []).length,
    configInconsistent: dto.config_inconsistent,
    configFields: dto.config_fields ?? [],
    sourceConfigs: dto.source_configs ?? [],
  }
}

export function fromContainerDto(dto: CherryPickContainerDto): CherryPickContainer {
  const sourceTasks = dto.source_tasks ?? []
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    executionStatus: dto.execution_status ?? dto.status,
    evaluationStatus: dto.evaluation_status ?? 'pending',
    totalCases: dto.total_cases,
    // is_cherry_pick=true → picked；否则（status=merged 整任务合并）→ whole
    mergeType: dto.is_cherry_pick ? 'picked' : 'whole',
    sourceTaskCount: sourceTasks.length,
    // 列表行未返 source_result_count，以 total_cases 近似
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
