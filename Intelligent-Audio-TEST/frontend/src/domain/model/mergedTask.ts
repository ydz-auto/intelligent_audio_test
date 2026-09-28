/**
 * 合并任务 Domain 模型（camelCase，零依赖，无索引签名兜底）
 * 对齐《任务合并功能设计文档》：type='merged' 的任务及其 TaskMergeRelation 来源任务。
 */

/** 合并任务来源任务摘要 */
export interface MergedTaskSource {
  id: number;
  name: string;
  status: string;
  totalCases?: number | null;
  completedCases?: number | null;
  failedCases?: number | null;
  createdAt?: string | null;
}

/** 合并任务列表项 */
export interface MergedTaskItem {
  id: number;
  name: string;
  description?: string | null;
  status: string;
  type: string;
  totalCases?: number | null;
  completedCases?: number | null;
  failedCases?: number | null;
  tags: string[];
  createdAt?: string | null;
  updatedAt?: string | null;
  sourceTasks: MergedTaskSource[];
}

/** 合并任务分页响应 */
export interface MergedTaskPage {
  items: MergedTaskItem[];
  total: number;
  page: number;
  perPage: number;
  pages: number;
}

/** 合并任务列表查询参数 */
export interface MergedTaskQuery {
  page?: number;
  perPage?: number;
  search?: string;
}
