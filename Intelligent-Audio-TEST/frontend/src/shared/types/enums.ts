/** 任务状态枚举 */
export const TaskStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  PAUSED: 'paused',
  STOPPED: 'stopped',
  SKIPPED: 'skipped',
  MERGED: 'merged',
} as const

/** 已结束的任务状态集合 */
export const FINISHED_STATUSES = [
  TaskStatus.COMPLETED,
  TaskStatus.FAILED,
  TaskStatus.STOPPED,
  TaskStatus.PAUSED,
  TaskStatus.SKIPPED,
  TaskStatus.MERGED,
] as const

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
  PENDING: 'pending',
  UPLOADING: 'uploading',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const

/** HTTP 状态码 */
export const HttpStatus = {
  OK: 200,
  CREATED: 201,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  NOT_FOUND: 404,
  SERVER_ERROR: 500,
} as const
