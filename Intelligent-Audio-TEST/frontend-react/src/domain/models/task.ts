/**
 * 任务域领域模型（domain 层，09_任务域.md §10 落位）。
 * 字段形态对照 api_gateway/schemas/task.py + published_task.py + data_transfer.py 实测 schema，
 * 后续接线仅替换 infrastructure/api 桩实现，页面与 hook 不返工（红线④）。
 * 状态枚举原值见 Vue frontend/src/domain/enums.ts（domain 层单一来源，这里照搬枚举语义）。
 */

/** 执行状态枚举（task.py execution_status：pending/queued/running/completed/failed/paused/stopped/skipped/merged） */
export type TaskExecutionStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'paused'
  | 'stopped'
  | 'skipped'
  | 'merged'

/** 评估状态枚举（evaluation_status：pending/evaluating/completed/failed/skipped） */
export type TaskEvaluationStatus =
  | 'pending'
  | 'evaluating'
  | 'completed'
  | 'failed'
  | 'skipped'

/** 任务类型派生分布（type_counts/列表类型：e2e/api/mixed，04_控制台.md §3.7.2） */
export type TaskType = 'e2e' | 'api' | 'mixed'

/** 任务列表项（task.py TaskListItem 平移） */
export interface TaskListItem {
  id: number
  name: string
  description: string | null
  /** 兼容旧口径 status（新口径走 execution_status/evaluation_status 双状态） */
  status: string
  execution_status: TaskExecutionStatus | null
  evaluation_status: TaskEvaluationStatus | null
  device_types: string[]
  config: Record<string, unknown>
  algorithm_type: string | null
  algorithm_params: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  total_cases: number | null
  case_count: number | null
  device_count: number | null
  completed_cases: number | null
  failed_cases: number | null
  /** API 数量（混合/API 任务派生，Vue 侧 task.device_count 之外补充） */
  api_count: number | null
  tags: string[]
  created_at: string | null
  updated_at: string | null
  is_favorite: boolean | null
  deleted: boolean | null
  deleted_at: string | null
  deleted_by_user_id: number | null
  reports: { count: number; reports: TaskReportItem[] } | null
  devices: TaskDeviceBrief[]
  apis: TaskApiBrief[]
  source_tasks: TaskSourceBrief[]
}

export interface TaskReportItem {
  id: number
  name: string | null
  status: string | null
  type: string | null
  created_at: string | null
}

export interface TaskDeviceBrief {
  id: number
  name: string
  status: string | null
  model: string | null
}

export interface TaskApiBrief {
  id: number
  name: string
  status: string | null
}

/** 合并任务来源任务摘要（task.py TaskSourceBrief） */
export interface TaskSourceBrief {
  id: number
  name: string
  status: string | null
  total_cases: number | null
  completed_cases: number | null
  failed_cases: number | null
  created_at: string | null
}

/** 任务域统计（task.py TaskDomainStatsData；徽章行与图表共用） */
export interface TaskDomainStats {
  total: number
  deleted_total: number
  status_counts: Record<string, number>
  type_counts: Record<TaskType, number>
  trend: Array<{ key: string; count: number }>
  granularity: 'day' | 'week' | 'month' | 'year'
}

/** 用例简报（task.py TaskCaseBrief） */
export interface TaskCaseBrief {
  case_id: string
  name: string
  status: string | null
  execution_status: string | null
  evaluation_status: string | null
  started_at: string | null
  completed_at: string | null
  duration: number | null
  /** 用例真实轮次数（后端取 test_cases.config.rounds 长度，缺省 1） */
  rounds_count?: number | null
  error_message: string | null
  group_name: string | null
  tags: string[]
  evaluation_dimensions: Array<{ id: number | string; name: string }>
  /** INT-734：该用例下是否存在人工复核结果（驱动「人工复核」Badge 显隐，19 规范 §3.5） */
  reviewed: boolean
}

/** 任务详情（task.py TaskDetailData） */
export interface TaskDetailData {
  id: number
  name: string
  description: string | null
  status: string
  execution_status: TaskExecutionStatus | null
  evaluation_status: TaskEvaluationStatus | null
  device_types: string[]
  config: Record<string, unknown>
  algorithm_type: string | null
  algorithm_params: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  expected_total_time: string | null
  expected_complete_time: string | null
  used_time: string | null
  total_cases: number | null
  case_count: number | null
  device_count: number | null
  completed_cases: number | null
  failed_cases: number | null
  tags: string[]
  cases: TaskCaseBrief[]
  devices: TaskDeviceBrief[]
  apis: TaskApiBrief[]
  created_at: string | null
  updated_at: string | null
  /** 关联资源摘要（详情卡信息格补充，mock 口径派生） */
  api_count: number | null
  concurrency: number | null
  /** INT-734：任务级已复核结果计数（驱动任务头/统计复核徽章，19 规范 §3.5） */
  review_count: number
}

/** 已发布任务列表项（published_task.py PublishedTaskItem） */
export interface PublishedTaskItem {
  id: number
  source_task_id: number | null
  name: string
  description: string | null
  type: 'api' | 'e2e' | null
  algorithm_type: string | null
  status: string
  benchmark: boolean
  version: number
  is_current: boolean
  version_count: number | null
  published_by: string | null
  published_at: string | null
  archived_at: string | null
  created_at: string | null
}

/** 已发布任务详情（published_task.py PublishedTaskDetailData 子集） */
export interface PublishedTaskDetail {
  id: number
  task_group_id: number | null
  source_task_id: number | null
  name: string
  description: string | null
  status: string
  benchmark: boolean
  version: number
  is_current: boolean
  snapshot_config: Record<string, unknown>
  has_task_snapshot: boolean
  publish_reason: string | null
  published_by: string | null
  published_at: string | null
  archived_by: string | null
  archived_at: string | null
  source_task_name: string | null
  source_task_status: string | null
  source_task_total_cases: number | null
  source_task_completed_cases: number | null
  report_snapshot: Record<string, unknown> | null
  has_report_snapshot: boolean
  versions: PublishedTaskItem[]
  execution_history: PublishedTaskExecutionItem[]
}

export interface PublishedTaskExecutionItem {
  task_id: number
  task_name: string
  version: number
  status: string
  total_cases: number
  completed_cases: number
  created_at: string | null
  completed_at: string | null
}

/** 挑选合并任务（type=cherry_pick，INT-339 §8 契约） */
export interface CherryPickTask {
  id: number
  name: string
  description: string | null
  status: string
  execution_status: TaskExecutionStatus
  evaluation_status: TaskEvaluationStatus
  total_cases: number | null
  source_task_count: number
  source_task_ids: number[]
  created_at: string | null
  is_favorite: boolean | null
}

/** 实时日志行（logs 域 log.py LogEntry 平移） */
export interface TaskLogEntry {
  id: number
  timestamp: string
  level: 'info' | 'warn' | 'error'
  message: string
}

/** 购物车条目（挑选合并，INT-339：按来源任务分组） */
export interface CartEntry {
  id: string
  sourceTaskId: number
  sourceTaskName: string
  caseName: string
  deviceName: string
  executionStatus: string
  evaluationStatus: string
}

/** 挑选集（另存为挑选集，可恢复进购物车/删除） */
export interface PickSet {
  id: string
  name: string
  createdAt: string
  entries: CartEntry[]
}
