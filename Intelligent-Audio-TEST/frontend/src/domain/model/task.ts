/**
 * Task 领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/task.py::TaskListItem / TaskDetailData
 */
import type { TaskStatusType, TaskType } from '../enums'

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
}

export interface Task {
  id: number | string
  name: string
  description?: string
  type: TaskType
  status: TaskStatusType
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
  result?: any
  reports?: {
    count: number
    reports: Array<{ id: number; name: string; status: string; type: string; createdAt?: string }>
  }
  devices?: TaskDeviceBrief[]
  apis?: TaskApiBrief[]
  /** 任务详情接口返回的关联测试用例列表（TaskDetailData.cases） */
  cases?: TaskCaseBrief[]
}

/** 任务创建表单/请求（前端 Domain → adapter 转 DTO；对齐 TaskCreateRequest 契约） */
export interface TaskCreateDraft {
  name: string
  type: TaskType
  description?: string
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
