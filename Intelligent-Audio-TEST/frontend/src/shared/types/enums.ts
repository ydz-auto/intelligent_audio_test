/** 任务状态枚举 */
export const TaskStatus = {
  PENDING: 'pending',
  QUEUED: 'queued',
  RUNNING: 'running',
  STARTING: 'starting',
  COMPLETED: 'completed',
  FAILED: 'failed',
  PAUSED: 'paused',
  STOPPED: 'stopped',
  SKIPPED: 'skipped',
  MERGED: 'merged',
  // 后端扩展状态（评估相关）
  EVALUATING: 'evaluating',
  REEVALUATING: 'reevaluating',
  REEVALUATE_QUEUED: 'reevaluate_queued',
} as const

/** 任务状态类型（由 TaskStatus 派生的字符串联合，供响应式状态标注使用） */
export type TaskStatusType = typeof TaskStatus[keyof typeof TaskStatus]

/** 已结束的任务状态集合 */
export const FINISHED_STATUSES = [
  TaskStatus.COMPLETED,
  TaskStatus.FAILED,
  TaskStatus.STOPPED,
  TaskStatus.PAUSED,
  TaskStatus.SKIPPED,
  TaskStatus.MERGED,
] as const

/** 用例执行状态枚举 */
export const ExecutionStatus = {
  PENDING: 'pending',
  QUEUED: 'queued',
  IN_PROGRESS: 'in_progress',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  STOPPED: 'stopped',
} as const

/** 用例评估状态枚举 */
export const EvaluationStatus = {
  PENDING: 'pending',
  QUEUED: 'queued',
  CALCULATING: 'calculating',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const

/** 测试类型枚举 */
export const TestType = {
  API: 'api',
  E2E: 'e2e',
} as const

/** 视图模式枚举 */
export const ViewMode = {
  ALL: 'all',
  GROUP: 'group',
  TAG: 'tag',
} as const

/** 上传状态枚举 */
export const UploadStatus = {
  IDLE: 'idle',
  PREPARING: 'preparing',
  PENDING: 'pending',
  UPLOADING: 'uploading',
  COMPLETED: 'completed',
  FAILED: 'failed',
  PAUSED: 'paused',
  STOPPED: 'stopped',
} as const

/** 报告状态枚举 */
export const ReportStatus = {
  COMPLETED: 'completed',
  FAILED: 'failed',
  RUNNING: 'running',
  DRAFT: 'draft',
  FINAL: 'final',
  PUBLISHED: 'published',
} as const

/** HTTP 状态码 */
export const HttpStatus = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  PARTIAL_CONTENT: 206,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  TOO_MANY_REQUESTS: 429,
  SERVER_ERROR: 500,
  INTERNAL_SERVER_ERROR: 500,
  BAD_GATEWAY: 502,
  SERVICE_UNAVAILABLE: 503,
  GATEWAY_TIMEOUT: 504,
} as const
