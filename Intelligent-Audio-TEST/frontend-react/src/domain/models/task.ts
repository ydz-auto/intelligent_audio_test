/**
 * 任务域领域模型（domain 层，09_任务域.md §10 落位）。
 * 字段一律 camelCase；后端 snake_case 契约（api_gateway/schemas/task.py +
 * published_task.py + data_transfer.py 实测 schema）到本模型的转换只在
 * infrastructure/adapters/dto/task-adapter.ts 完成（架构红线：前端只见 camelCase 领域对象）。
 * 状态枚举原值见 Vue frontend/src/domain/enums.ts（domain 层单一来源，这里照搬枚举语义）。
 */

/** 执行状态枚举（后端 task.py `execution_status`：pending/queued/running/completed/failed/paused/stopped/skipped/merged） */
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

/** 评估状态枚举（后端 `evaluation_status`：pending/evaluating/completed/failed/skipped） */
export type TaskEvaluationStatus =
  | 'pending'
  | 'evaluating'
  | 'completed'
  | 'failed'
  | 'skipped'

/** 任务类型派生分布（后端 `type_counts`/列表类型：e2e/api/mixed，04_控制台.md §3.7.2） */
export type TaskType = 'e2e' | 'api' | 'mixed'

/** 任务列表项（task.py TaskListItem 平移） */
export interface TaskListItem {
  id: number
  name: string
  description: string | null
  /** 兼容旧口径 status（新口径走 executionStatus/evaluationStatus 双状态） */
  status: string
  executionStatus: TaskExecutionStatus | null
  evaluationStatus: TaskEvaluationStatus | null
  deviceTypes: string[]
  config: Record<string, unknown>
  algorithmType: string | null
  algorithmParams: Record<string, unknown> | null
  startedAt: string | null
  completedAt: string | null
  totalCases: number | null
  caseCount: number | null
  deviceCount: number | null
  completedCases: number | null
  failedCases: number | null
  /** API 数量（混合/API 任务派生，Vue 侧 task.deviceCount 之外补充） */
  apiCount: number | null
  tags: string[]
  createdAt: string | null
  updatedAt: string | null
  isFavorite: boolean | null
  /** 挑选合并容器标记（TaskCherryPickRelation 存在性判定，INT-339） */
  isCherryPick: boolean
  /** 合并方式（whole=整任务合并 / picked=结果挑选；普通任务 null，INT-577） */
  mergeType: MergeType | null
  /** 容器来源任务数（列表次行「来源 {n} 个任务」，INT-577） */
  sourceTaskCount: number | null
  /** 容器来源结果数（列表次行「· 结果 {m} 条」，INT-577；上游可缺省） */
  sourceResultCount: number | null
  deleted: boolean | null
  deletedAt: string | null
  deletedByUserId: number | null
  reports: { count: number; reports: TaskReportItem[] } | null
  devices: TaskDeviceBrief[]
  apis: TaskApiBrief[]
  sourceTasks: TaskSourceBrief[]
}

/** 合并容器的合并方式（task.py TaskListItem.mergeType：whole / picked） */
export type MergeType = 'whole' | 'picked'

export interface TaskReportItem {
  id: number
  name: string | null
  status: string | null
  type: string | null
  createdAt: string | null
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
  totalCases: number | null
  completedCases: number | null
  failedCases: number | null
  createdAt: string | null
}

/** 任务域统计（task.py TaskDomainStatsData；徽章行与图表共用） */
export interface TaskDomainStats {
  total: number
  deletedTotal: number
  statusCounts: Record<string, number>
  typeCounts: Record<TaskType, number>
  trend: Array<{ key: string; count: number }>
  granularity: 'day' | 'week' | 'month' | 'year'
}

/** 用例简报（task.py TaskCaseBrief） */
export interface TaskCaseBrief {
  caseId: string
  name: string
  status: string | null
  executionStatus: string | null
  evaluationStatus: string | null
  startedAt: string | null
  completedAt: string | null
  duration: number | null
  /** 用例真实轮次数（后端取 test_cases.config.rounds 长度，缺省 1） */
  roundsCount?: number | null
  errorMessage: string | null
  groupName: string | null
  tags: string[]
  evaluationDimensions: Array<{ id: number | string; name: string }>
  /** INT-734：该用例下是否存在人工复核结果（驱动「人工复核」Badge 显隐，19 规范 §3.5） */
  reviewed: boolean
  /** 用例级执行目标数（一个用例 × 多 API/设备；执行行已合并进 targets） */
  targetCount?: number | null
  /** 执行目标明细（API/设备维度，供详情内逐目标对比） */
  targets?: TaskCaseTarget[]
}

/** 用例执行目标（TaskCase 行级：API 行 deviceId 即 apis.id） */
export interface TaskCaseTarget {
  taskCaseId: number
  targetType?: 'api' | 'device' | null
  deviceType: string | null
  deviceId: string | null
  apiId: number | null
  targetName?: string | null
  status: string | null
  executionStatus: string | null
  evaluationStatus: string | null
  startedAt: string | null
  completedAt: string | null
  duration: number | null
  errorMessage: string | null
}

/** 任务详情（task.py TaskDetailData） */
export interface TaskDetailData {
  id: number
  name: string
  description: string | null
  status: string
  executionStatus: TaskExecutionStatus | null
  evaluationStatus: TaskEvaluationStatus | null
  deviceTypes: string[]
  config: Record<string, unknown>
  algorithmType: string | null
  algorithmParams: Record<string, unknown> | null
  startedAt: string | null
  completedAt: string | null
  expectedTotalTime: string | null
  expectedCompleteTime: string | null
  usedTime: string | null
  totalCases: number | null
  caseCount: number | null
  deviceCount: number | null
  completedCases: number | null
  failedCases: number | null
  tags: string[]
  cases: TaskCaseBrief[]
  devices: TaskDeviceBrief[]
  apis: TaskApiBrief[]
  createdAt: string | null
  updatedAt: string | null
  /** 关联资源摘要（详情卡信息格补充，mock 口径派生） */
  apiCount: number | null
  concurrency: number | null
  /** 任务级已复核结果计数（INT-734：驱动任务头/统计复核徽章，19 规范 §3.5；>0 时重执行/重评估走硬确认层，§5.7） */
  reviewCount: number
}

/** 已发布任务列表项（published_task.py PublishedTaskItem） */
export interface PublishedTaskItem {
  id: number
  sourceTaskId: number | null
  name: string
  description: string | null
  type: 'api' | 'e2e' | null
  algorithmType: string | null
  status: string
  benchmark: boolean
  version: number
  isCurrent: boolean
  versionCount: number | null
  publishedBy: string | null
  publishedAt: string | null
  archivedAt: string | null
  createdAt: string | null
}

/** 已发布任务详情（published_task.py PublishedTaskDetailData 子集） */
export interface PublishedTaskDetail {
  id: number
  taskGroupId: number | null
  sourceTaskId: number | null
  name: string
  description: string | null
  status: string
  benchmark: boolean
  version: number
  isCurrent: boolean
  snapshotConfig: Record<string, unknown>
  hasTaskSnapshot: boolean
  publishReason: string | null
  publishedBy: string | null
  publishedAt: string | null
  archivedBy: string | null
  archivedAt: string | null
  sourceTaskName: string | null
  sourceTaskStatus: string | null
  sourceTaskTotalCases: number | null
  sourceTaskCompletedCases: number | null
  reportSnapshot: Record<string, unknown> | null
  hasReportSnapshot: boolean
  versions: PublishedTaskItem[]
  executionHistory: PublishedTaskExecutionItem[]
}

export interface PublishedTaskExecutionItem {
  taskId: number
  taskName: string
  version: number
  status: string
  totalCases: number
  completedCases: number
  createdAt: string | null
  completedAt: string | null
}

/** 已发布任务执行结果（published_task.py PublishedTaskExecuteData；POST /published-tasks/{id}/execute 创建出的日常任务） */
export interface PublishedTaskExecuteResult {
  taskId: number
  taskName: string
  publishedTaskId: number
  publishedTaskVersion: number
}

// ---------------------------------------------------------------------------
// 冻结快照（§5.13 冻结任务详情 / 冻结报告数据源）
// `PublishedTaskDetail.snapshotConfig` / `reportSnapshot` 为后端不透明明文
// JSON（契约保持 camelCase，对齐 publishedTask.ts 快照结构），此处给出页面渲染
// 用的类型化读法；snake_case↔camelCase 不做转换（快照即冻结形态）。
// ---------------------------------------------------------------------------

/** 任务详情冻结体（INT-303，schemaVersion=2）：任务详情真冻结，与 reportSnapshot 同一语义 */
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

/** 从 `snapshotConfig` 不透明明文中读取任务详情冻结体（无则 null → legacy 历史版本态） */
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

/** 从 `reportSnapshot` 中读取报告快照（无则 null → 空态「该快照缺少可渲染的冻结报告数据」） */
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
  executionStatus: TaskExecutionStatus
  evaluationStatus: TaskEvaluationStatus
  totalCases: number | null
  sourceTaskCount: number
  sourceTaskIds: number[]
  createdAt: string | null
  isFavorite: boolean | null
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
