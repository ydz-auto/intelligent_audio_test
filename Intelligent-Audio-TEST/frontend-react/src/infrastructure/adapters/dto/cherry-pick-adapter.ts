/**
 * 挑选合并 DTO→Domain 转换器（infrastructure/adapters/dto，18_挑选合并交互重设计.md §7.3，INT-713）。
 * snake_case 唯一出现层；前端只见 camelCase Domain。
 * 对照契约：cherry_pick_bp.py + task_service/application/task/cherry_pick_service.py 实测响应。
 * §11-2/§11-5 落地后（INT-762 审计）：candidates 已返 case_name/device_name/api_name/
 * result_type/algorithm_type，购物车快照已返 source_case_name/source_device_name/
 * source_result_type（source_api_name 缺省 undefined）——adapter 直取；
 * 缺名（后端返回 null / case_id 兜底）时经 name map 二次装饰，仍缺则降级显示 ID。
 */
import type {
  CherryPickCandidate,
  CherryPickContainer,
  CherryPickSourceTask,
  PickCartEntry,
  PickCartGroup,
  PickDuplicate,
  PickPreview,
  PickSet,
} from '@/domain/models/cherryPick'
import type {
  CherryPickCandidateDto,
  CherryPickCartGroupDto,
  CherryPickCartItemDto,
  CherryPickPreviewDto,
  CherryPickSetListItemDto,
  TaskContainerItemDto,
  TaskSourceBriefDto,
} from '@/infrastructure/dto/cherry-pick.dto'

/** 名称装饰 map（api 层预取的设备/API/用例名，缺省 null → 降级显示 ID） */
export interface PickNameMaps {
  devices: Map<number, string>
  apis: Map<number, string>
  cases: Map<string, string>
}

export const EMPTY_NAME_MAPS: PickNameMaps = {
  devices: new Map(),
  apis: new Map(),
  cases: new Map(),
}

export function fromCandidateDto(
  dto: CherryPickCandidateDto,
  names: PickNameMaps = EMPTY_NAME_MAPS
): CherryPickCandidate {
  // §11-2：后端缺名时 case_name 兜底返回 case_id 原文 → 判等降级（不裸显 UUID，
  // 走「用例不可用 {前 8 位 id}…」友好文案）；name map 仅作二次装饰补充。
  const caseName =
    dto.case_name && dto.case_name !== dto.case_id
      ? dto.case_name
      : names.cases.get(dto.case_id) ?? null
  return {
    resultId: dto.result_id,
    taskId: dto.task_id,
    taskName: dto.task_name,
    caseId: dto.case_id,
    caseName,
    deviceId: dto.device_id,
    deviceName:
      dto.device_name ??
      (dto.device_id != null ? names.devices.get(dto.device_id) ?? null : null),
    apiId: dto.api_id,
    apiName:
      dto.api_name ?? (dto.api_id != null ? names.apis.get(dto.api_id) ?? null : null),
    resultType: dto.result_type && dto.result_type.trim() ? dto.result_type : null,
    algorithmType: dto.algorithm_type && dto.algorithm_type.trim() ? dto.algorithm_type : null,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluated ? 'completed' : 'pending',
    evaluated: dto.evaluated,
    createdAt: dto.created_at,
  }
}

export function fromCartEntryDto(
  dto: CherryPickCartItemDto,
  names: PickNameMaps = EMPTY_NAME_MAPS
): PickCartEntry {
  return {
    itemId: String(dto.item_id),
    resultId: dto.result_id,
    sourceTaskId: dto.source_task_id,
    sourceTaskName: dto.source_task_name ?? `任务 ${dto.source_task_id}`,
    sourceCaseId: dto.source_case_id,
    sourceCaseName:
      dto.source_case_name && dto.source_case_name.trim()
        ? dto.source_case_name
        : dto.source_case_id != null
          ? names.cases.get(dto.source_case_id) ?? null
          : null, // INT-577 §11-5：cart_get 已返 source_case_name → 直取；缺省回退 name map，仍缺则树层降级
    sourceDeviceId: dto.source_device_id,
    sourceDeviceName:
      dto.source_device_name && dto.source_device_name.trim()
        ? dto.source_device_name
        : dto.source_device_id != null
          ? names.devices.get(dto.source_device_id) ?? null
          : null,
    sourceApiId: dto.source_api_id,
    sourceApiName:
      dto.source_api_name && dto.source_api_name.trim()
        ? dto.source_api_name
        : dto.source_api_id != null
          ? names.apis.get(dto.source_api_id) ?? null
          : null,
    sourceResultType:
      dto.source_result_type && dto.source_result_type.trim()
        ? dto.source_result_type
        : null, // §11-5 历史快照缺 source_result_type → 折叠「结果类型待补充」
    executionStatus: dto.execution_status,
    evaluationStatus: null, // 快照未含评估状态 → 显示「—」
    invalid: dto.invalid,
  }
}

export function fromCartGroupDto(
  dto: CherryPickCartGroupDto,
  names: PickNameMaps = EMPTY_NAME_MAPS
): PickCartGroup {
  return {
    taskId: dto.source_task_id,
    taskName: dto.source_task_name ?? `任务 ${dto.source_task_id}`,
    entries: dto.items.map((it) => fromCartEntryDto(it, names)),
  }
}

export function fromSetListItemDto(dto: CherryPickSetListItemDto): PickSet {
  return {
    setId: String(dto.set_id),
    name: dto.name,
    createdAt: dto.created_at,
    itemCount: dto.item_count,
    entries: [],
  }
}

export function fromPreviewDto(dto: CherryPickPreviewDto): PickPreview {
  return {
    totalResults: dto.total_results,
    invalidResultIds: dto.invalid_result_ids,
    sourceTaskCount: dto.source_task_count,
    deviceIds: dto.device_ids,
    deviceNames: dto.device_names?.filter((n): n is string => n != null) ?? undefined,
    caseCount: dto.case_count,
    executionStatusCounts: dto.execution_status_counts,
    duplicates: (dto.duplicates ?? []).map(
      (d): PickDuplicate => ({
        deviceId: d.device_id,
        caseId: d.case_id,
        count: d.count,
      })
    ),
    // 后端 preview 未返配置差异（§11 FEAT）→ 可选字段缺省不展示
  }
}

/** 来源任务简报 → 领域 source task（resultCount 取 completed_cases 兜底 total_cases） */
function fromSourceTaskDto(dto: TaskSourceBriefDto): CherryPickSourceTask {
  return {
    id: dto.id,
    name: dto.name,
    resultCount: dto.completed_cases ?? dto.total_cases ?? 0,
    status: dto.status ?? '',
  }
}

export interface ContainerDtoWithType extends TaskContainerItemDto {
  /** 容器归属：merged=true → whole；cherry_pick=true → picked */
  mergeType: 'whole' | 'picked'
}

export function fromContainerDto(
  dto: ContainerDtoWithType,
  /** picked 容器溯源补充（source_trace 组聚合；缺省空） */
  sourceResults: { source_task_id: number; source_task_name: string | null; count: number }[] = []
): CherryPickContainer {
  let sourceTasks = dto.source_tasks.map(fromSourceTaskDto)
  let sourceTaskCount = sourceTasks.length
  let sourceResultCount = sourceTasks.reduce((sum, t) => sum + t.resultCount, 0)
  // 后端 read model 对 cherry-pick 容器未填 source_tasks（§11 FEAT 待补），
  // 客户端经溯源端点聚合补全（source_trace 返回 任务→结果 分组）
  if (dto.mergeType === 'picked' && sourceTasks.length === 0 && sourceResults.length > 0) {
    sourceTasks = sourceResults.map((g) => ({
      id: g.source_task_id,
      name: g.source_task_name ?? `任务 ${g.source_task_id}`,
      resultCount: g.count,
      status: '',
    }))
    sourceTaskCount = sourceTasks.length
    sourceResultCount = sourceTasks.reduce((sum, t) => sum + t.resultCount, 0)
  }
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    totalCases: dto.total_cases,
    mergeType: dto.mergeType,
    sourceTaskCount,
    sourceResultCount,
    sourceTaskIds: sourceTasks.map((t) => t.id),
    sourceTasks,
    createdAt: dto.created_at ?? '',
    isFavorite: dto.is_favorite,
  }
}
