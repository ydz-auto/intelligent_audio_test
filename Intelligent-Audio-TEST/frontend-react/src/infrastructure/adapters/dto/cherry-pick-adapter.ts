/**
 * 挑选合并 DTO→Domain 转换器（infrastructure/adapters/dto，18_挑选合并交互重设计.md §7.3，INT-713）。
 * snake_case 唯一出现层；前端只见 camelCase Domain。
 * 对照契约：cherry_pick_bp.py + task_service/application/task/cherry_pick_service.py 实测响应。
 * §11-2/§11-5 落地后（INT-762 审计）：candidates 已返 case_name/device_name/api_name/
 * result_type/algorithm_type，购物车快照已返 source_case_name/source_device_name/
 * source_result_type（source_api_name 缺省 undefined）——adapter 直取；
 * 缺名（后端返回 null / case_id 兜底）时经 name map 二次装饰，仍缺则降级显示 ID。
 * INT-1497 §11-7：candidates 另返 tags/group_id/group_name/duration/rounds，adapter 转
 * tags/groupId/groupName/totalDuration/rounds，用例层组织与用例卡直接消费。
 */
import type {
  CherryPickCandidate,
  CherryPickContainer,
  CherryPickSourceTask,
  ContainerSourceGroup,
  ContainerSourceResult,
  ContainerSourceTrace,
  PickableTask,
  PickCandidateTree,
  PickCartEntry,
  PickCartGroup,
  PickDuplicate,
  PickPreview,
  PickSet,
} from '@/domain/models/cherryPick'
import type {
  CherryPickCandidateDto,
  CherryPickCandidateTreeDto,
  CherryPickCartGroupDto,
  CherryPickCartItemDto,
  CherryPickPreviewDto,
  CherryPickSetListItemDto,
  CherryPickSourceTraceDto,
  PickableTaskDto,
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
    // INT-1497 §11-7：用例域真名（标签/分组/时长/轮次）→ camelCase Domain；
    // 后端缺省（null）才落降级：tags=[] 归「未设置标签」桶、groupId=null 归「未分组」桶。
    tags: dto.tags ?? [],
    groupId: dto.group_id,
    groupName: dto.group_name,
    totalDuration: dto.duration,
    rounds: dto.rounds,
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

/**
 * 阶段 2 候选树 DTO → Domain（GET /tasks/cherry-picks/candidates/tree，INT-1510 §8.2）。
 * 缺名口径按 INT-1824 §8.2.8：接口不拼文案——
 *   `case_name === case_id`（用例目录查不到/已软删）→ caseName = null（前端出「未知用例」）；
 *   `device_name === null`（设备已软删）→ deviceName = null（前端出「未知设备」）。
 */
export function fromCandidateTreeDto(
  dto: CherryPickCandidateTreeDto
): PickCandidateTree {
  return {
    total: dto.total ?? 0,
    taskCount: dto.task_count ?? 0,
    meta: {
      tasks: (dto.meta?.tasks ?? []).map((t) => ({
        taskId: t.task_id,
        taskName: t.task_name,
        taskStatus: t.task_status,
      })),
      cases: (dto.meta?.cases ?? []).map((c) => ({
        caseId: c.case_id,
        caseName:
          c.case_name && c.case_name.trim() && c.case_name !== c.case_id
            ? c.case_name
            : null,
        algorithmType: c.algorithm_type,
        tags: c.tags ?? [],
        groupId: c.group_id,
        groupName: c.group_name,
        duration: c.duration,
        rounds: c.rounds,
      })),
      devices: (dto.meta?.devices ?? []).map((d) => ({
        deviceId: d.device_id,
        deviceName: d.device_name,
      })),
      apis: (dto.meta?.apis ?? []).map((a) => ({
        apiId: a.api_id,
        apiName: a.api_name,
      })),
    },
    tree: (dto.tree ?? []).map((taskNode) => ({
      taskId: taskNode.task_id,
      count: taskNode.count,
      cases: (taskNode.cases ?? []).map((caseNode) => ({
        caseId: caseNode.case_id,
        count: caseNode.count,
        devices: (caseNode.devices ?? []).map((deviceNode) => ({
          deviceId: deviceNode.device_id,
          apiId: deviceNode.api_id,
          count: deviceNode.count,
          resultTypes: (deviceNode.result_types ?? []).map((rtNode) => ({
            // 领域模型恒为 string；后端 result_type 可为 NULL（缺值桶）→ 归一到空串
            // （`isPendingResultType` 把 '' / 'default' / null 同归「结果类型待补充」）
            resultType: rtNode.result_type ?? '',
            count: rtNode.count,
            resultIds: rtNode.result_ids ?? [],
          })),
        })),
      })),
    })),
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
    // INT-1693 §11-7：cart_get 逐行补用例域真名（与候选行同口径）→ 购物车/复核的用例层组织
    // 出真分组/真标签名；历史条目缺省时 tags=[] 归「未设置标签」、groupId/Name=null 归「未分组」。
    sourceTags: dto.tags ?? [],
    sourceGroupId: dto.group_id ?? null,
    sourceGroupName: dto.group_name ?? null,
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
  // 后端容器计数（INT-577 read model）优先：`source_tasks[].total_cases` 是**源任务用例数**，
  // 不等于本次挑选的结果条数（实测容器 3 源 / 4 结果会算成 139），不能用它代替结果数。
  let sourceTaskCount = dto.source_task_count ?? sourceTasks.length
  let sourceResultCount =
    dto.source_result_count ??
    sourceTasks.reduce((sum, t) => sum + t.resultCount, 0)
  // 后端 read model 对 cherry-pick 容器未填 source_tasks 时（旧口径），
  // 客户端经溯源端点聚合补全（source_trace 返回 任务→结果 分组）
  if (dto.mergeType === 'picked' && sourceTasks.length === 0 && sourceResults.length > 0) {
    sourceTasks = sourceResults.map((g) => ({
      id: g.source_task_id,
      name: g.source_task_name ?? `任务 ${g.source_task_id}`,
      resultCount: g.count,
      status: '',
    }))
    sourceTaskCount = dto.source_task_count ?? sourceTasks.length
    sourceResultCount =
      dto.source_result_count ??
      sourceTasks.reduce((sum, t) => sum + t.resultCount, 0)
  }
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    totalCases: dto.total_cases,
    // §5.5.4 列表「部分失败」映射：case_count 优先（= 容器用例数），缺省退回 total_cases
    caseCount: dto.case_count ?? dto.total_cases ?? null,
    failedCases: dto.failed_cases ?? null,
    mergeType: dto.mergeType,
    sourceTaskCount,
    sourceResultCount,
    sourceTaskIds: sourceTasks.map((t) => t.id),
    sourceTasks,
    createdAt: dto.created_at ?? '',
    isFavorite: dto.is_favorite,
    // 容器报告摘要（「查看报告」跳转数据源；后端返 null → 无报告禁用该项）
    reports: dto.reports,
  }
}

/** 可挑选任务行 DTO→Domain（INT-1496 §8.1：pickable_count→count、
 *  execution_status→executionStatus（**任务**状态）、created_at 直接映射） */
export function fromPickableTaskDto(dto: PickableTaskDto): PickableTask {
  return {
    taskId: dto.id,
    taskName: dto.name,
    executionStatus: dto.execution_status,
    createdAt: dto.created_at,
    count: dto.pickable_count,
  }
}

/**
 * 容器溯源 DTO → Domain（§5.5.1 实测只到 id 级；§11-8 新增的结果级字段直取，
 * 未返回时为 null，前端按 §5.5.4 降级口径处理，不改树结构）。
 */
export function fromSourceTraceDto(
  dto: CherryPickSourceTraceDto
): ContainerSourceTrace {
  return {
    taskId: dto.task_id,
    isCherryPick: dto.is_cherry_pick,
    total: dto.total,
    groups: (dto.groups ?? []).map(
      (g): ContainerSourceGroup => ({
        sourceTaskId: g.source_task_id,
        sourceTaskName: g.source_task_name ?? null,
        sourceTaskStatus: g.source_task_status ?? null,
        results: (g.results ?? []).map(
          (r): ContainerSourceResult => ({
            resultId: r.result_id,
            sourceCaseId: r.source_case_id ?? null,
            sourceDeviceId: r.source_device_id ?? null,
            sourceApiId: r.source_api_id ?? null,
            missing: r.missing === true,
            resultType: r.result_type?.trim() ? r.result_type : null,
            executionStatus: r.execution_status?.trim() ? r.execution_status : null,
            evaluated: r.evaluated ?? null,
            caseName: r.case_name?.trim() ? r.case_name : null,
            deviceName: r.device_name?.trim() ? r.device_name : null,
            apiName: r.api_name?.trim() ? r.api_name : null,
            // 取结果时间只认 §11-8 的 result_created_at；r.created_at 是关系行时间（并入容器的时间），
            // 语义不同且实测 5 条叶行同值（= 容器 created_at），不得顶替（INT-1711 审计 P2-1）
            resultCreatedAt: r.result_created_at ?? null,
          })
        ),
      })
    ),
  }
}
