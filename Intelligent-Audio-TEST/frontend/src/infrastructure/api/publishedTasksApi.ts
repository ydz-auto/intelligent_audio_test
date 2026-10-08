/**
 * Published Tasks API module
 * 出口契约：Domain（camelCase）；snake_case 转换全部收敛在本文件（Infrastructure 独占）。
 */
import { request, type RequestOptions } from '../http/client';
import type {
  PublishedTaskDetail,
  PublishedTaskExecuteResult,
  PublishedTaskItem,
  PublishedTaskPage,
  PublishedTaskStatus,
  ReportSnapshot,
} from '../../domain/model/publishedTask';

/** 后端返回的 snake_case 列表项（DTO） */
interface PublishedTaskItemDto {
  id: number;
  source_task_id?: number | null;
  name: string;
  description?: string | null;
  type: string;
  status: PublishedTaskStatus;
  version: number;
  is_current: boolean;
  version_count?: number;
  published_by?: string | null;
  published_at?: string | null;
  archived_at?: string | null;
  created_at?: string | null;
}

/** 后端返回的分页 DTO */
interface PublishedTaskPageDto {
  items: PublishedTaskItemDto[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

/** 后端返回的详情 DTO（snake_case） */
interface PublishedTaskDetailDto extends Omit<PublishedTaskItemDto, 'version_count'> {
  task_group_id?: number | null;
  snapshot_config: Record<string, unknown>;
  publish_reason?: string | null;
  archived_by?: string | null;
  source_task_name?: string | null;
  source_task_status?: string | null;
  source_task_total_cases?: number | null;
  source_task_completed_cases?: number | null;
  report_snapshot?: ReportSnapshot | null;
  has_report_snapshot: boolean;
  versions: PublishedTaskItemDto[];
  execution_history: {
    task_id: number;
    task_name: string;
    version: number;
    status: string;
    total_cases: number;
    completed_cases: number;
    created_at?: string | null;
    completed_at?: string | null;
  }[];
}

/** snake_case 列表项 DTO → camelCase Domain 模型 */
function toPublishedTaskItem(raw: PublishedTaskItemDto): PublishedTaskItem {
  return {
    id: raw.id,
    sourceTaskId: raw.source_task_id ?? undefined,
    name: raw.name,
    description: raw.description ?? undefined,
    type: raw.type,
    status: raw.status,
    version: raw.version,
    isCurrent: raw.is_current,
    versionCount: raw.version_count,
    publishedBy: raw.published_by ?? undefined,
    publishedAt: raw.published_at ?? undefined,
    archivedAt: raw.archived_at ?? undefined,
    createdAt: raw.created_at ?? undefined,
  };
}

/** camelCase 查询参数 → snake_case HTTP query（后端契约） */
function toQueryParams(params: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {};
  for (const [key, value] of Object.entries(params)) {
    const snakeKey =
      key === 'perPage' ? 'per_page'
      : key === 'startDate' ? 'start_date'
      : key === 'endDate' ? 'end_date'
      : key;
    if (value !== undefined && value !== null && value !== '') {
      result[snakeKey] = value;
    }
  }
  return result;
}

export const publishedTasksApi = {
  /** 当前版本列表（分页 + status/keyword/type/时间筛选）→ PublishedTaskPage（camelCase） */
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}): Promise<PublishedTaskPage> {
    const dto = await request<PublishedTaskPageDto>('GET', '/published-tasks', null, {
      ...options,
      params: toQueryParams(params),
    });
    return {
      items: (dto?.items ?? []).map(toPublishedTaskItem),
      total: dto?.total ?? 0,
      page: dto?.page ?? 1,
      perPage: dto?.per_page ?? 10,
      pages: dto?.pages ?? 0,
    };
  },

  /** 详情（版本历史 + 来源摘要 + 执行历史 + 冻结报告）→ PublishedTaskDetail（camelCase） */
  async getOne(id: number): Promise<PublishedTaskDetail> {
    const dto = await request<PublishedTaskDetailDto>('GET', `/published-tasks/${id}`);
    return {
      id: dto.id,
      taskGroupId: dto.task_group_id ?? undefined,
      sourceTaskId: dto.source_task_id ?? undefined,
      name: dto.name,
      description: dto.description ?? undefined,
      type: dto.type,
      status: dto.status,
      version: dto.version,
      isCurrent: dto.is_current,
      snapshotConfig: (dto.snapshot_config ?? {}) as unknown as PublishedTaskDetail['snapshotConfig'],
      publishReason: dto.publish_reason ?? undefined,
      publishedBy: dto.published_by ?? undefined,
      publishedAt: dto.published_at ?? undefined,
      archivedBy: dto.archived_by ?? undefined,
      archivedAt: dto.archived_at ?? undefined,
      sourceTaskName: dto.source_task_name ?? undefined,
      sourceTaskStatus: dto.source_task_status ?? undefined,
      sourceTaskTotalCases: dto.source_task_total_cases ?? undefined,
      sourceTaskCompletedCases: dto.source_task_completed_cases ?? undefined,
      reportSnapshot: dto.report_snapshot ?? undefined,
      hasReportSnapshot: dto.has_report_snapshot ?? false,
      versions: (dto.versions ?? []).map((v) => ({
        ...toPublishedTaskItem(v),
        publishReason: dto.publish_reason ?? undefined,
      })),
      executionHistory: (dto.execution_history ?? []).map((e) => ({
        taskId: e.task_id,
        taskName: e.task_name,
        version: e.version,
        status: e.status,
        totalCases: e.total_cases,
        completedCases: e.completed_cases,
        createdAt: e.created_at ?? undefined,
        completedAt: e.completed_at ?? undefined,
      })),
    };
  },

  /** 发布：日常任务 → 已发布任务 v1（请求体 snake_case） */
  async publish(payload: { sourceTaskId: number; name: string; description?: string; publishReason?: string }) {
    const body: Record<string, any> = {
      source_task_id: payload.sourceTaskId,
      name: payload.name,
    };
    if (payload.description) body.description = payload.description;
    if (payload.publishReason) body.publish_reason = payload.publishReason;
    const raw = await request<{ id: number }>('POST', '/published-tasks', body);
    return { id: raw?.id };
  },

  /** 执行：按快照创建新的日常任务 → PublishedTaskExecuteResult（camelCase） */
  async execute(id: number): Promise<PublishedTaskExecuteResult> {
    const raw = await request<{
      task_id: number;
      task_name: string;
      published_task_id: number;
      published_task_version: number;
    }>('POST', `/published-tasks/${id}/execute`);
    return {
      taskId: raw.task_id,
      taskName: raw.task_name,
      publishedTaskId: raw.published_task_id,
      publishedTaskVersion: raw.published_task_version,
    };
  },

  /** 创建新版本（vN → vN+1，旧版本 is_current=False） */
  async createVersion(id: number, payload: { sourceTaskId?: number; name?: string; description?: string; publishReason?: string }) {
    const body: Record<string, any> = {};
    if (payload.sourceTaskId != null) body.source_task_id = payload.sourceTaskId;
    if (payload.name) body.name = payload.name;
    if (payload.description) body.description = payload.description;
    if (payload.publishReason) body.publish_reason = payload.publishReason;
    const raw = await request<{ id: number }>('POST', `/published-tasks/${id}/versions`, body);
    return { id: raw?.id };
  },

  /** 归档（幂等） */
  async archive(id: number) {
    return request<{ id: number; status: string }>('POST', `/published-tasks/${id}/archive`);
  },

  /** 重命名（作用于整个版本链） */
  async update(id: number, payload: { name: string }) {
    return request<{ id: number; name: string }>('PUT', `/published-tasks/${id}`, { name: payload.name });
  },
};
