/**
 * Task 领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/task.py::TaskListItem / TaskDetailData
 */
import type { TaskStatusType, VisibilityType, DeviceTypeType } from '../enums'
import { DeviceType } from '../enums'
import { resolveApiDeviceType } from './device'

/** 逐目标执行模式（INT-1115：parallel=并行/默认，serial=串行；复用全局旧 ExecutionMode 口径） */
export type ExecutionMode = 'parallel' | 'serial'

/** 逐目标执行模式条目（INT-1115 §5.2.4：列表顺序 = 选中顺序 = 串行链顺序） */
export interface TargetMode {
  /** 目标类型（device=设备 / api=被测 API） */
  targetType: 'device' | 'api'
  /** 目标 id（device.id / apis.id，int） */
  targetId: number
  /** 该目标执行模式（缺省并行；串行仅等同类道内前序终态后启动） */
  mode: ExecutionMode
}

/** 任务关联设备简报 */
export interface TaskDeviceBrief {
  id: number
  name: string
  status?: string
  model?: string
}

/** 任务关联 API 简报 */
export interface TaskApiBrief {
  id: number
  name: string
  status?: string
}

/** 合并任务来源任务摘要（TaskMergeRelation 源任务简报） */
export interface TaskSourceBrief {
  id: number
  name: string
  status?: string
  totalCases?: number | null
  completedCases?: number | null
  failedCases?: number | null
  createdAt?: string | null
}

/** 任务关联测试用例简报（TaskCaseBrief → camelCase） */
export interface TaskCaseBrief {
  caseId: string
  name: string
  status?: string
  executionStatus?: string
  evaluationStatus?: string
  startedAt?: string
  completedAt?: string
  duration?: number
  errorMessage?: string
  groupName?: string
  tags?: string[]
  /** INT-302/F3：本任务用例聚合的评估维度（重评估维度勾选候选集） */
  evaluationDimensions?: Array<{ id: number; name: string }>
  /** INT-340：该用例下是否存在人工复核结果（任务详情「人工复核」标记） */
  reviewed?: boolean
}

/** 用例移除结果（INT-305：执行详情模态窗删除用例；DELETE /tasks/{id}/cases/{caseId}） */
export interface TaskCaseRemoveResult {
  taskId: string
  caseId: string
  /** true = 移除成功（恒 true，与 HTTP 200 同义；保留语义字段便于区分幂等） */
  removed: boolean
  /** true = 幂等重复删除（该用例此前已被移除，无新副作用） */
  idempotent: boolean
  /** true = 待执行阶段物理删除（purge）；false = 软删留痕 + 结果 excluded */
  purged: boolean
  /** 终态任务触发报告重算 */
  reportRequeued: boolean
}

/** 用例级被测设备选择（INT-1434：对应后端 TaskCaseDeviceAssignment）
 *
 * 每个任务用例可独立指定被测设备类型与 ID（物理设备 / HTTP API / WebSocket API），
 * 为空时保持旧语义（后端按用例配置形态派生兜底）。device_type 取值见 DeviceType 枚举。
 */
export interface TaskCaseDeviceAssignment {
  /** 用例 ID（字符串契约，后端 TaskCase.test_case_id） */
  caseId: string
  /** 被测设备类型（physical / http_api / websocket_api，DeviceType 枚举原值） */
  deviceType?: DeviceTypeType
  /** 目标 ID：physical=设备 ID，http_api/websocket_api=API ID（后端 TaskCase.device_id 字符串契约） */
  deviceId?: string | number
  /** 所属实验室 ID（可选，多实验室扩展） */
  labId?: number
}

/** 用例级被测设备选择组装入参（buildCaseDeviceAssignments） */
export interface BuildCaseDeviceAssignmentsOptions {
  caseIds: (string | number)[]
  deviceIds: (string | number)[]
  apis: Array<{
    id: string | number
    /** 【历史遗留】显式 device_type（后端读侧已不再返回；仅旧数据兜底） */
    deviceType?: string | null
    /** INT-2025：流式性——执行亲和域的唯一判据（true → websocket_api，false → http_api） */
    streaming?: boolean | null
    endpointUrl?: string
  }>
}

/**
 * 组装用例级被测设备选择（INT-1434 / INT-2025）：按「所选用例 × 选中目标」生成笛卡尔积。
 * - 物理设备目标 → { device_type: physical, device_id: 设备 id }
 * - API 目标 → 亲和域只由流式性派生（INT-2025 / 后端 B0 裁定：流式 → websocket_api，
 *   非流式 → http_api）；旧数据缺 streaming 时回退「显式 device_type → 端点协议」口径。
 */
export function buildCaseDeviceAssignments(options: BuildCaseDeviceAssignmentsOptions): TaskCaseDeviceAssignment[] {
  const { caseIds, deviceIds, apis } = options
  const assignments: TaskCaseDeviceAssignment[] = []
  for (const rawCaseId of caseIds) {
    const caseId = String(rawCaseId)
    for (const deviceId of deviceIds) {
      assignments.push({ caseId, deviceType: DeviceType.PHYSICAL, deviceId })
    }
    for (const api of apis) {
      let deviceType: DeviceTypeType
      if (api.streaming === true) {
        deviceType = DeviceType.WEBSOCKET_API
      } else if (api.streaming === false) {
        deviceType = DeviceType.HTTP_API
      } else {
        deviceType = (api.deviceType || resolveApiDeviceType(api.endpointUrl)) as DeviceTypeType
      }
      assignments.push({ caseId, deviceType, deviceId: api.id })
    }
  }
  return assignments
}

export interface Task {
  id: number | string
  name: string
  description?: string
  /** 用例级被测设备类型集合（physical/http_api/websocket_api，差异#2 收尾取代 task.type） */
  deviceTypes?: string[]
  status: TaskStatusType
  /** INT-301：任务级执行状态（纯执行域，评估推进不落此字段；缺省回退 status） */
  executionStatus?: TaskStatusType | string
  /** INT-301：任务级评估状态（pending/evaluating/completed/failed/skipped） */
  evaluationStatus?: string
  progress?: number
  config?: Record<string, any>
  algorithmType?: string
  algorithmParams?: Record<string, any>
  startedAt?: string
  completedAt?: string
  /** 预计总耗时（格式化文本，如 "12分钟"） */
  expectedTotalTime?: string | number
  /** 预计完成时间 */
  expectedCompleteTime?: string
  /** 已耗时（格式化文本） */
  usedTime?: string
  totalCases?: number
  caseCount?: number
  deviceCount?: number
  completedCases?: number
  failedCases?: number
  /** INT-340：任务下已复核结果条数（覆盖提醒硬确认 + 报告页「人工复核」标记） */
  reviewCount?: number
  tags?: string[]
  createdAt?: string
  updatedAt?: string
  finishedAt?: string
  error?: string
  deleted?: boolean
  /** INT-215：回收站字段（删除人为 user_id，AUTH_MODE=off 时 NULL） */
  deletedAt?: string
  deletedByUserId?: number | null
  /** INT-339：挑选合并容器标记（专有关系表存在性判定） */
  isCherryPick?: boolean
  /** INT-577：统一合并容器「合并方式」（whole=整任务合并 / picked=结果挑选） */
  mergeType?: 'whole' | 'picked' | null
  /** INT-577：容器来源任务数 / 来源结果数（列表次行「来源 {n} 任务 · 结果 {m} 条」） */
  sourceTaskCount?: number | null
  sourceResultCount?: number | null
  /** INT-423/467：资源可见性（shared/private；私有仅 owner+admin 可见） */
  visibility?: VisibilityType
  /** INT-423/467：资源归属人 user_id（owner 判定；缺失时按非私有处理） */
  createdByUserId?: number | null
  result?: any
  reports?: {
    count: number
    reports: Array<{ id: number; name: string; status: string; type: string; createdAt?: string }>
  }
  devices?: TaskDeviceBrief[]
  apis?: TaskApiBrief[]
  /** 合并任务来源任务列表（由 TaskMergeRelation 填充，存在即合并容器任务） */
  sourceTasks?: TaskSourceBrief[]
  /** 任务详情接口返回的关联测试用例列表（TaskDetailData.cases） */
  cases?: TaskCaseBrief[]
}

/** INT-577：合并容器统计（GET /tasks stats 块；merged ∪ cherry_pick 并集，供「挑选合并」页签计数/facet） */
export interface TaskContainerStats {
  total: number
  whole: number
  picked: number
}

/** 任务创建表单/请求（前端 Domain → adapter 转 DTO；对齐 TaskCreateRequest 契约） */
export interface TaskCreateDraft {
  name: string
  description?: string
  /** INT-282：执行口径（api/e2e，TestType 域枚举值）。基线契约显式携带；
   * 注：V9.7.31 后端 task.type 已废弃（归类由用例级 device_type 派生），
   * 网关 extra="ignore" 静默忽略，仅作契约兼容留痕 */
  type?: string
  /** INT-423/467：新建可见性（默认 shared；私有仅 owner 可访问） */
  visibility?: VisibilityType
  /** 对应 case_ids: List[str]（后端用例 ID 为字符串） */
  caseIds: string[]
  /** 对应 device_ids: List[int] */
  deviceIds?: number[]
  /** 对应 api_ids: List[int] */
  apiIds?: number[]
  /** INT-1434：用例级被测设备选择（所选用例 × 选中目标 笛卡尔积；缺省后端派生兜底，零回归） */
  caseDevices?: TaskCaseDeviceAssignment[]
  /** INT-1115：逐目标执行模式（列表顺序 = 选中顺序 = 串行链顺序；缺省/空数组 = 全目标并行）。
   * 废弃顶层 execution_mode/serial_first：后端提交旧字段一律 422，前端不再携带 */
  targetModes?: TargetMode[]
  tags?: string[]
  algorithmType?: string
  algorithmParams?: Record<string, any>
  config?: Record<string, any>
}

/** 任务域全量聚合统计（INT-200：统计卡与图表数据源，与列表分页无关） */
export interface TaskDomainStats {
  /** 未删除任务总数 */
  total: number
  /** 回收站（软删除）任务总数 */
  deletedTotal: number
  /** 未删除任务按状态计数（status → count，含评估/合并等全部状态） */
  statusCounts: Record<string, number>
  /** 类型派生分布（用例级 device_type 派生：api/e2e/mixed） */
  typeCounts: { api: number; e2e: number; mixed: number }
  /** 完成任务按 createdAt 分桶（键格式与图表粒度对应：日 YYYY-M-D / 周 YYYY-Wn / 月 YYYY-MM / 年 YYYY） */
  trend: { key: string; count: number }[]
  /** trend 分桶粒度 day/week/month/year */
  granularity: string
}
