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
  /** 挑选合并容器标记（TaskCherryPickRelation 存在性判定，INT-339） */
  is_cherry_pick: boolean
  /** 合并方式（whole=整任务合并 / picked=结果挑选；普通任务 null，INT-577） */
  merge_type: MergeType | null
  /** 容器来源任务数（列表次行「来源 {n} 个任务」，INT-577） */
  source_task_count: number | null
  /** 容器来源结果数（列表次行「· 结果 {m} 条」，INT-577；上游可缺省） */
  source_result_count: number | null
  deleted: boolean | null
  deleted_at: string | null
  deleted_by_user_id: number | null
  reports: { count: number; reports: TaskReportItem[] } | null
  devices: TaskDeviceBrief[]
  apis: TaskApiBrief[]
  source_tasks: TaskSourceBrief[]
}

/** 合并容器的合并方式（task.py TaskListItem.merge_type：whole / picked） */
export type MergeType = 'whole' | 'picked'

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
  /** 任务级已复核结果计数（INT-734：驱动任务头/统计复核徽章，19 规范 §3.5；>0 时重执行/重评估走硬确认层，§5.7） */
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

/** 已发布任务执行结果（published_task.py PublishedTaskExecuteData；POST /published-tasks/{id}/execute 创建出的日常任务） */
export interface PublishedTaskExecuteResult {
  task_id: number
  task_name: string
  published_task_id: number
  published_task_version: number
}

// ---------------------------------------------------------------------------
// 冻结快照（§5.13 冻结任务详情 / 冻结报告数据源）
// `PublishedTaskDetail.snapshot_config` / `report_snapshot` 为后端不透明明文
// JSON（契约保持 camelCase，对齐 publishedTask.ts 快照结构），此处给出页面渲染
// 用的类型化读法；snake_case↔camelCase 不做转换（快照即冻结形态）。
// ---------------------------------------------------------------------------

/** 任务详情冻结体（INT-303，schemaVersion=2）：任务详情真冻结，与 report_snapshot 同一语义 */
export interface TaskSnapshot {
  /** 冻结契约版本（2 = 含参考参数内容内联的完整冻结） */
  schemaVersion?: number
  task: {
    name?: string | null
    description?: string | null
    config?: Record<string, unknown>
    algorithmType?: string | null
    algorithmParams?: Record<string, unknown> | null
    tags?: string[]
  }
  /** 用例完整配置深拷贝（rounds/音频引用/播放设备/标签/分组/评价维度/算法参数/参考参数内容内联） */
  cases: TaskSnapshotCase[]
  /** 关联被测设备引用快照（含名称，渲染不再 join 现库） */
  devices?: TaskSnapshotRef[]
  /** 关联 API 引用快照（含名称） */
  apis?: TaskSnapshotRef[]
  /** 关联播放设备引用快照（含名称） */
  playbackDevices?: TaskSnapshotRef[]
}

/** 冻结体引用项（ID + 发布时冻结的名称；名称可能为 null——服务不可达降级仅 ID） */
export interface TaskSnapshotRef {
  id: number
  name?: string | null
}

/** 冻结体中的单个用例（发布时完整配置快照） */
export interface TaskSnapshotCase {
  caseId: string
  name?: string | null
  description?: string | null
  config?: Record<string, unknown>
  algorithmType?: string | null
  algorithmParams?: Record<string, unknown> | null
  /** 参考参数内容内联（[{roundNumber, referenceParams, path}]，可独立还原） */
  referenceParams?: TaskSnapshotRefParams[]
  /** 参考参数源路径留档（[roundNumber, path]） */
  referenceParamsSource?: { roundNumber?: number | null; path?: string | null }[]
  tags?: string[]
  group?: { id: string; name: string; description?: string | null; algorithmType?: string | null } | null
  /** 用例级执行路由快照（physical/http_api/websocket_api） */
  deviceType?: string | null
  deviceId?: string | null
  labId?: number | null
}

/** 冻结体中的单轮参考参数（内容内联） */
export interface TaskSnapshotRefParams {
  roundNumber?: number | null
  referenceParams: unknown[]
  path?: string | null
}

/**
 * 报告快照（发布时冻结的真实报告：引用 sourceReportId + 报告 7 表冻结数据，不可变）。
 * INT-258 快照语义：版本详情按冻结数据渲染成报告样，不受源报告修改/删除影响。
 */
export interface ReportSnapshot {
  /** 冻结契约版本（2 = 7 表完整冻结；存量 v1 快照缺省） */
  schemaVersion?: number
  /** 引用轨：源报告 ID（关联 test_reports，提供跳转报告页入口） */
  sourceReportId?: number | null
  /** 兼容字段（V9.7.10 冻结契约遗留，语义同 sourceReportId） */
  reportId?: number
  name: string
  type?: string | null
  status: string
  description?: string | null
  analysis?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  summary?: {
    totalCases?: number
    completedCases?: number
    failedCases?: number
    passRate?: number
    duration?: number
    startedAt?: string | null
    completedAt?: string | null
    [key: string]: unknown
  }
  cases?: ReportSnapshotCase[]
}

/** 冻结报告中的单个用例（逐轮结果/评估数据/日志） */
export interface ReportSnapshotCase {
  /** 报告用例行 ID（schemaVersion=2 起冻结；旧快照缺省由前端合成兜底） */
  id?: number | null
  testCaseId?: string | null
  name?: string | null
  description?: string | null
  category?: string | null
  /** 标签名数组（读模型已归一化；后端快照原始形态为 `{ name }` 对象数组，INT-1650） */
  tags: string[]
  metrics: Record<string, unknown>
  algorithmType?: string | null
  logs?: string | null
}

/** 从 `snapshot_config` 不透明明文中读取任务详情冻结体（无则 null → legacy 历史版本态） */
export function readTaskSnapshot(config: Record<string, unknown>): TaskSnapshot | null {
  const raw = config?.taskSnapshot
  if (raw == null || typeof raw !== 'object') return null
  return raw as unknown as TaskSnapshot
}

/**
 * 快照标签归一化（INT-1650）：后端报告/任务快照里的 `tags` 是对象数组（`{ name }`），
 * 存量快照也可能已是字符串数组；统一收敛成标签名数组，空值剔除。
 * 视图层只消费 `string[]`，不再各处分类型判断。
 */
export function toTagNames(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((tag) => {
      if (typeof tag === 'string') return tag
      if (tag != null && typeof tag === 'object' && 'name' in tag) {
        const name = (tag as { name?: unknown }).name
        return name == null ? '' : String(name)
      }
      return ''
    })
    .filter((name) => name.length > 0)
}

/** 从 `report_snapshot` 中读取报告快照（无则 null → 空态「该快照缺少可渲染的冻结报告数据」） */
export function readReportSnapshot(report: Record<string, unknown> | null): ReportSnapshot | null {
  if (report == null || typeof report !== 'object') return null
  const snapshot = report as unknown as ReportSnapshot
  if (!Array.isArray(snapshot.cases)) return snapshot
  return {
    ...snapshot,
    cases: snapshot.cases.map((c) => ({
      ...c,
      tags: toTagNames((c as { tags?: unknown }).tags),
    })),
  }
}

/** 冻结报告摘要读取（schemaVersion=2 走 summary；存量 v1 快照走平铺 caseCount/passRate 回落） */
export function readReportSummary(report: ReportSnapshot | null): {
  caseCount: number | null
  passRate: number | null
  completedCases: number | null
  failedCases: number | null
  duration: number | null
} {
  const legacy = report as (ReportSnapshot & { caseCount?: unknown; passRate?: unknown }) | null
  return {
    caseCount:
      report?.summary?.totalCases ??
      (typeof legacy?.caseCount === 'number' ? legacy.caseCount : null),
    passRate:
      report?.summary?.passRate ??
      (typeof legacy?.passRate === 'number' ? legacy.passRate : null),
    completedCases: report?.summary?.completedCases ?? null,
    failedCases: report?.summary?.failedCases ?? null,
    duration: report?.summary?.duration ?? null,
  }
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

/** 重新执行发起结果（POST /tasks/{id}/retry 响应；camelCase Domain） */
export interface TaskRetryResult {
  taskId: string | number
  status: string
}

/** 重新评估发起结果（POST /evaluation/task/reevaluate 响应；camelCase Domain） */
export interface TaskReevaluateResult {
  totalCases: number
  queuedCases: number
  reextractedCases: number
  message: string
}
