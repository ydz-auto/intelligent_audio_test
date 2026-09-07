/**
 * TaskProgress 领域模型 —— camelCase
 * 对应后端契约 shared/schemas/socket_payloads.py::TaskProgressPayload，
 * 经 infrastructure/adapters/taskProgressAdapter.ts 转换后供业务层消费。
 */
import type { TaskStatusType } from '../enums'

/** 当前执行用例（Socket 进度里的 current_case） */
export interface TaskProgressCurrentCase {
  caseId: string
  name: string
  step?: string
  startTime: number
}

/** HTTP 轮询通道的当前用例（TaskProgressCurrentCase：started_at → startedAt） */
export interface TaskProgressHttpCurrentCase {
  caseId: string
  name: string
  step?: string
  startedAt?: string
}

/** 用例进度条目（Socket 进度里的 test_cases） */
export interface TaskProgressCaseItem {
  id: string
  status: string
  executionStatus: string
  evaluationStatus: string
  duration: number
  errorMessage: string
  roundProgress?: { current: number; total: number }
}

/** API 资源并发状态（Socket 进度里的 api_resources） */
export interface TaskProgressApiResource {
  id: string
  name: string
  currentConcurrent: number
  queueLength: number
  avgResponseTime: number
  maxConcurrent: number
}

/** Socket 进度日志条目（转换后的 camelCase 日志） */
export interface TaskProgressLog {
  id: number
  level: string
  message: string
  timestamp: number
}

/** 任务进度 ReadModel（Socket 通道共用结构） */
export interface TaskProgress {
  taskId: string
  status: TaskStatusType
  totalProgress: number
  completedCount: number
  inProgressCount: number
  executionFailedCount: number
  evaluationFailedCount: number
  totalCount: number
  currentCase: TaskProgressCurrentCase | null
  testCases: TaskProgressCaseItem[]
  logs: TaskProgressLog[]
  apiResources: TaskProgressApiResource[]
  expectedTotalTime: string | number | null
  expectedCompleteTime: string | null
  usedTime: string
}

/** 任务进度 HTTP 轮询 ReadModel（TaskProgressData：total_cases/completed_cases/failed_cases/progress） */
export interface TaskProgressHttp {
  taskId: string
  status: TaskStatusType
  totalCases: number
  completedCases: number
  failedCases: number
  progress: number
  currentCase: TaskProgressHttpCurrentCase | null
  updatedAt?: string
}

/** 任务启动响应（POST /tasks/{id}/start → camelCase） */
export interface TaskStartResult {
  taskId: string
  status: TaskStatusType | string
  expectedTotalTime?: string | number | null
  expectedCompleteTime?: string | null
}

/** 用例进度展示模型（任务执行页"关联用例"列表使用） */
export interface AssociatedCase {
  id: string | number
  name?: string
  status: string
  executionStatus: string
  evaluationStatus: string
  duration?: string
  roundProgress?: { current: number; total: number }
  /** 用例分组名，用于"用例分组视图" */
  groupName?: string
  /** 用例标签，用于"标签视图" */
  tags?: string[] | { id: number; name: string }[]
  /** 算法类型 */
  algorithmType?: string
}

/** API 资源并发状态（任务执行页展示使用） */
export interface APIResource {
  id: string | number
  name: string
  currentConcurrent: number
  queueLength: number
  avgResponseTime: number
  maxConcurrent: number
}
