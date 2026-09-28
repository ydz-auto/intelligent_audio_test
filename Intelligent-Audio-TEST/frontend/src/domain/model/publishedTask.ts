/**
 * 已发布任务 Domain 模型（camelCase，零依赖，无索引签名兜底）
 * 对齐《任务发布功能设计文档》：从日常任务发布、不可变版本快照、可执行/归档。
 */

/** 已发布任务状态 */
export type PublishedTaskStatus = 'published' | 'archived';

/** 配置快照（发布时冻结的完整配置，执行时据此创建日常任务） */
export interface PublishedTaskSnapshot {
  caseIds: string[];
  deviceIds: number[];
  apiIds: number[];
  config: Record<string, unknown>;
  algorithmType?: string | null;
  algorithmParams: Record<string, unknown>;
  tags: string[];
  sourceTaskId: number;
}

/** 已发布任务列表项 */
export interface PublishedTaskItem {
  id: number;
  sourceTaskId?: number | null;
  name: string;
  description?: string | null;
  type: string;
  status: PublishedTaskStatus;
  version: number;
  isCurrent: boolean;
  versionCount?: number;
  publishedBy?: string | null;
  publishedAt?: string | null;
  archivedAt?: string | null;
  createdAt?: string | null;
}

/** 已发布任务版本列表项（详情内嵌） */
export interface PublishedTaskVersion extends PublishedTaskItem {
  publishReason?: string | null;
}

/** 已发布任务版本产生的执行记录（由该版本创建并执行的日常任务） */
export interface PublishedTaskExecutionItem {
  taskId: number;
  taskName: string;
  version: number;
  status: string;
  totalCases: number;
  completedCases: number;
  createdAt?: string | null;
  completedAt?: string | null;
}

/** 报告快照（发布时冻结的执行产物：报告/用例结果/评估数据/用例日志，不可变） */
export interface ReportSnapshot {
  reportId: number;
  name: string;
  type: string;
  status: string;
  description?: string | null;
  analysis?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  summary: {
    totalCases: number;
    completedCases: number;
    failedCases: number;
    passRate: number;
    duration: number;
    startedAt?: string | null;
    completedAt?: string | null;
    caseCategories: unknown[];
    allMetrics: unknown[];
    dimensionValues: unknown[];
    devices: unknown[];
    apis: unknown[];
    deviceStats: unknown[];
    apiStats: unknown[];
    metricData: Record<string, unknown>;
    tagMetricData: Record<string, unknown>;
  };
  cases: ReportSnapshotCase[];
}

/** 冻结报告中的单个用例 */
export interface ReportSnapshotCase {
  testCaseId?: string | null;
  name?: string | null;
  description?: string | null;
  category?: string | null;
  tags: unknown[];
  metrics: Record<string, unknown>;
  results: unknown[];
  audios: unknown[];
  referenceParams: Record<string, unknown>;
  algorithmResults: Record<string, unknown>;
  algorithmType?: string | null;
  logs?: string | null;
}

/** 已发布任务详情 */
export interface PublishedTaskDetail {
  id: number;
  taskGroupId?: number | null;
  sourceTaskId?: number | null;
  name: string;
  description?: string | null;
  type: string;
  status: PublishedTaskStatus;
  version: number;
  isCurrent: boolean;
  snapshotConfig: PublishedTaskSnapshot;
  publishReason?: string | null;
  publishedBy?: string | null;
  publishedAt?: string | null;
  archivedBy?: string | null;
  archivedAt?: string | null;
  sourceTaskName?: string | null;
  sourceTaskStatus?: string | null;
  sourceTaskTotalCases?: number | null;
  sourceTaskCompletedCases?: number | null;
  reportSnapshot?: ReportSnapshot | null;
  hasReportSnapshot: boolean;
  versions: PublishedTaskVersion[];
  executionHistory: PublishedTaskExecutionItem[];
}

/** 分页响应 */
export interface PublishedTaskPage {
  items: PublishedTaskItem[];
  total: number;
  page: number;
  perPage: number;
  pages: number;
}

/** 执行已发布任务返回的新日常任务 */
export interface PublishedTaskExecuteResult {
  taskId: number;
  taskName: string;
  publishedTaskId: number;
  publishedTaskVersion: number;
}

/** 已发布任务列表查询参数 */
export interface PublishedTaskQuery {
  page?: number;
  perPage?: number;
  status?: PublishedTaskStatus | '';
  keyword?: string;
  type?: string;
}
