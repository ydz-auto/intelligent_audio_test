/**
 * 领域层 —— camelCase 领域模型
 *
 * 规则：
 * - 一律 camelCase，组件/composable 只允许访问本层字段
 * - Enum 值保持后端原值（如 reevaluate_queued），只有字段名转换
 * - 本层禁止 import infrastructure/（依赖方向单向向下）
 */

// ===== 状态枚举（值 = 后端原值，禁止改动） =====
export {
  TaskStatus,
  ExecutionStatus,
  EvaluationStatus,
  TestType,
  ViewMode,
  UploadStatus,
  ReportStatus,
  HttpStatus,
  FINISHED_STATUSES,
} from '../enums'
export type { TaskStatusType, TaskType } from '../enums'

// ===== 通用 =====

/**
 * 通用 API 响应契约（业务层 Service 出口统一信封，camelCase）
 * data 必填：Infrastructure 已解包成功载荷/失败兜底，业务层无需再判空收窄
 */
export interface APIResponse<T = any> {
  success: boolean
  code: number
  message: string
  data: T
  detail?: any
  total?: number
  error?: string
  headers?: Record<string, string>
  isBinary?: boolean
  calibratedCount?: number
  uncalibratedCount?: number
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  perPage: number
  pages: number
}

/** 报告摘要引用（任务卡片展示用） */
export interface ReportBrief {
  id: number
  name: string
  status: string
  type: string
  createdAt?: string
}

/** 分页信息（前端 Domain，camelCase） */
export interface PaginationInfo {
  page: number
  pages: number
  perPage: number
  total: number
}

/** 分页结果（API 层出口契约：扁平结构，camelCase；与 Paginated<T> 等价） */
export type PaginatedResult<T> = Paginated<T>

/**
 * 列表接口响应（可选分页字段窄化别名）
 * 部分后端接口分页字段可能缺省（deviceFetching 等消费方做数组/分页双兜底）
 */
export type ListResponse<T> = Partial<Pick<Paginated<T>, 'items' | 'pages' | 'total'>>
