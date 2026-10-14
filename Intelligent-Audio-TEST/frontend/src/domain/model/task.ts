/**
 * Task 领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/task.py::TaskListItem / TaskDetailData
 */
import type { TaskStatusType } from '../enums'

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
}

/** 用例移除结果（INT-305：执行详情模态窗删除用例；DELETE /tasks/{id}/cases/{caseId}） */
export interface TaskCaseRemoveResult {
  taskId: string
  caseId: string
  /** true = 待执行阶段物理删除（purge）；false = 软删留痕 + 结果 excluded */
  purged: boolean
  /** 终态任务触发报告重算 */
  reportRequeued: boolean
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
  tags?: string[]
  createdAt?: string
  updatedAt?: string
  finishedAt?: string
  error?: string
  deleted?: boolean
  /** INT-215：回收站字段（删除人为 user_id，AUTH_MODE=off 时 NULL） */
  deletedAt?: string
  deletedByUserId?: number | null
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

/** 任务创建表单/请求（前端 Domain → adapter 转 DTO；对齐 TaskCreateRequest 契约） */
export interface TaskCreateDraft {
  name: string
  description?: string
  /** INT-282：执行口径（api/e2e，TestType 域枚举值）。基线契约显式携带；
   * 注：V9.7.31 后端 task.type 已废弃（归类由用例级 device_type 派生），
   * 网关 extra="ignore" 静默忽略，仅作契约兼容留痕 */
  type?: string
  /** 对应 case_ids: List[str]（后端用例 ID 为字符串） */
  caseIds: string[]
  /** 对应 device_ids: List[int] */
  deviceIds?: number[]
  /** 对应 api_ids: List[int] */
  apiIds?: number[]
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
