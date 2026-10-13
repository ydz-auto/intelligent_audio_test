/**
 * 已发布任务 Domain 模型（camelCase，零依赖，无索引签名兜底）
 * 对齐《任务发布功能设计文档》：从日常任务发布、不可变版本快照、可执行/归档。
 * 迁移自 V9.7.10 frontend/src/domain/model/publishedTask.ts。
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
  /** Benchmark 测试集标识（发布时显式指定则随快照冻结，排行分组用） */
  benchmarkSuite?: string | null;
  /** Benchmark 被测类别（asr/voice_llm/tts/translation，发布时显式指定则随快照冻结） */
  benchmarkCategory?: string | null;
}

/** 已发布任务列表项 */
export interface PublishedTaskItem {
  id: number;
  sourceTaskId?: number | null;
  name: string;
  description?: string | null;
  /** 任务类型 api/e2e（发布时由快照用例级 device_type 派生，对齐 V9.7.10） */
  type?: string | null;
  /** 关联算法类型（发布时从快照冻结） */
  algorithmType?: string | null;
  status: PublishedTaskStatus;
  /** 是否参与 Benchmark 排行（published_tasks.benchmark 行级布尔列） */
  benchmark: boolean;
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

/**
 * 报告快照（发布时冻结的真实报告：引用 sourceReportId + 报告 7 表冻结数据，不可变）。
 * INT-258 快照语义：版本详情按冻结数据渲染成报告样（对齐报告页），
 * 不受后续源报告修改/删除影响；schemaVersion=2 起为 7 表完整冻结。
 */
export interface ReportSnapshot {
  /** 冻结契约版本（2 = 7 表完整冻结；存量 v1 快照缺省） */
  schemaVersion?: number;
  /** 引用轨：源报告 ID（关联 test_reports，提供跳转报告页入口） */
  sourceReportId?: number | null;
  /** 兼容字段（V9.7.10 冻结契约遗留，语义同 sourceReportId） */
  reportId: number;
  name: string;
  type?: string | null;
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
    allCaseTags?: unknown[];
    allMetrics: unknown[];
    dimensionValues: unknown[];
    devices: unknown[];
    apis: unknown[];
    resources?: unknown[];
    resourceHeaders?: unknown[];
    fieldMappings?: Record<string, unknown>;
    deviceStats: unknown[];
    apiStats: unknown[];
    metricData: Record<string, unknown> | unknown[];
    tagMetricData: Record<string, unknown> | unknown[];
    tagCategoryMetricData?: unknown[];
    caseTypeStats?: unknown[];
    rawData?: unknown[];
  };
  cases: ReportSnapshotCase[];
}

/** 冻结报告中的单个用例（逐轮结果/评估数据/日志） */
export interface ReportSnapshotCase {
  /** 报告用例行 ID（schemaVersion=2 起冻结；旧快照缺省由前端合成兜底） */
  id?: number | null;
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
  status: PublishedTaskStatus;
  /** 是否参与 Benchmark 排行（published_tasks.benchmark 行级布尔列） */
  benchmark: boolean;
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
