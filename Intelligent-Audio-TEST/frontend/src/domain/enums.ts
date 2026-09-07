/** 领域枚举定义 —— 值 = 后端原值，禁止改动值；文件为 domain 层单一来源 */
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

/** 任务类型（值 = 后端原值） */
export type TaskType = 'api' | 'e2e' | 'playback' | 'evaluation' | 'report' | 'task' | 'execution' | 'comparison' | 'performance' | 'stress' | 'audio_import'

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

/** 字段类型枚举（值 = 后端 shared.models.common_enums.FieldType 原值，禁止改动值） */
export const FieldType = {
  RTTM: 'rttm',
  STM: 'stm',
  TEXT: 'text',
  AUDIO_FILE: 'audio_file',
  AUDIO: 'audio',
  NUMBER: 'number',
  BOOLEAN: 'boolean',
  JSON: 'json',
  TIMESTAMP: 'timestamp',
} as const

/** 字段类型（由 FieldType 派生的字符串联合） */
export type FieldTypeType = typeof FieldType[keyof typeof FieldType]

/** 报告状态枚举 */
export const ReportStatus = {
  COMPLETED: 'completed',
  FAILED: 'failed',
  RUNNING: 'running',
  DRAFT: 'draft',
  FINAL: 'final',
  PUBLISHED: 'published',
  GENERATING: 'generating',
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

/** 设备状态枚举（值 = 后端 status 字段原值，禁止改动值） */
export const DeviceStatus = {
  ONLINE: 'online',
  OFFLINE: 'offline',
  TESTING: 'testing',
} as const

/** 设备状态类型（含后端扩展值兜底，供 domain/model/device.ts 引用） */
export type DeviceStatusType = typeof DeviceStatus[keyof typeof DeviceStatus] | (string & {})

/** 日志级别枚举（值 = 后端 level 查询参数原值，大写） */
export const LogLevel = {
  DEBUG: 'DEBUG',
  INFO: 'INFO',
  WARNING: 'WARNING',
  ERROR: 'ERROR',
} as const

/** 日志级别类型 */
export type LogLevelType = typeof LogLevel[keyof typeof LogLevel]

/** API 端点/配置状态枚举（值 = 后端 status 字段原值，禁止改动值） */
export const ApiEndpointStatus = {
  ONLINE: 'online',
  OFFLINE: 'offline',
  BUSY: 'busy',
  ERROR: 'error',
} as const

/** API 端点/配置状态类型 */
export type ApiEndpointStatusType = typeof ApiEndpointStatus[keyof typeof ApiEndpointStatus]
