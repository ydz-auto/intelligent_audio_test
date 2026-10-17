/**
 * Tasks API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 */
import { request, type RequestOptions } from '../http/client';
import { toTask, toTaskList, toTaskCreateDto, toCaseDetail, toCaseResults, toTaskDomainStats, toTaskCaseRemoveResult, toContainerStats } from '../adapters/taskAdapter';
import { toTaskProgressHttp, toTaskStartResult } from '../adapters/taskProgressAdapter';
import { toPaginated } from '../adapters/commonAdapter';
import type {
  TaskDto,
  TaskDetailDto,
  TaskStartDto,
  PaginatedDto,
  TaskBatchActionDto,
  TaskMergeDto,
  TaskUpdateCasesRequestDto,
  TaskListQueryDto,
  TaskDomainStatsDto,
  TaskContainerStatsDto,
} from '../dto';
import type { TaskProgressHttpDto } from '../dto/taskProgressDto';
import type { Task, TaskCreateDraft, TaskDomainStats, TaskCaseRemoveResult } from '../../domain/model/task';
import type { CaseDetail, CaseResults } from '../../domain/model/taskCaseDetail';
import type { TaskProgress } from '../../domain/model/taskProgress';

/** 人工复核历史条目（INT-340：原值/新值/备注/操作人/时间） */
export interface ReviewHistoryItem {
  id: number
  resultId: number
  taskId: number
  testCaseId?: string | null
  fieldName: 'execution_status' | 'evaluation_status'
  oldValue?: string | null
  newValue: string
  comment: string
  createdByUserId?: number | null
  createdAt?: string | null
}

/** 任务列表查询参数（camelCase 域契约；snake_case 化在本文件内部完成） */
export interface TaskListQuery {
  page?: number
  perPage?: number
  /** 原始 Task.status 过滤（历史兼容；执行域筛选请用 executionStatus） */
  status?: string
  algorithmType?: string
  search?: string
  startTime?: string
  endTime?: string
  // INT-216 补接线：useTaskList（INT-141）已传参但此处映射缺失导致静默丢弃
  favorite?: boolean
  deleted?: boolean
  // INT-301：评估状态过滤（与执行状态并列）
  evaluationStatus?: string
  // INT-298：merged=true 仅合并容器任务（对齐 V9.7.10 合并页签数据源）
  merged?: boolean
  // INT-339：cherry_pick=true 仅挑选合并容器任务（挑选合并页签数据源）
  cherryPick?: boolean
  // INT-577：合并方式快捷筛选（whole|picked）
  mergeType?: 'whole' | 'picked'
  // INT-577：返回合并容器统计块（merged ∪ cherry_pick 并集；挑选合并页签计数/facet 数据源）
  stats?: boolean
  // INT-301 F1：执行状态过滤（复用派生口径，命中行执行徽章 == 筛选值）
  executionStatus?: string
  // INT-423/467：可见性过滤（private|shared；服务端行级过滤）
  visibility?: string
  // INT-273：派生任务类型过滤（api/e2e/mixed）
  taskType?: string
}

/** camelCase 任务查询 → snake_case HTTP query（后端 TaskListQueryDto 契约） */
function toTaskListQueryDto(query: TaskListQuery): TaskListQueryDto {
  const dto: TaskListQueryDto = { page: query.page ?? 1, per_page: query.perPage ?? 10 }
  if (query.status !== undefined) dto.status = query.status
  if (query.algorithmType !== undefined) dto.algorithm_type = query.algorithmType
  if (query.search !== undefined) dto.search = query.search
  if (query.startTime !== undefined) dto.start_date = query.startTime
  if (query.endTime !== undefined) dto.end_date = query.endTime
  // INT-216：收藏 / 回收站过滤（同名透传；后端 TaskListQuery.favorite/deleted）
  if (query.favorite !== undefined) dto.favorite = query.favorite
  if (query.deleted !== undefined) dto.deleted = query.deleted
  // INT-301：评估状态过滤
  if (query.evaluationStatus !== undefined) dto.evaluation_status = query.evaluationStatus
  // INT-298：合并容器任务过滤
  if (query.merged !== undefined) dto.merged = query.merged
  // INT-339：挑选合并容器任务过滤
  if (query.cherryPick !== undefined) dto.cherry_pick = query.cherryPick
  // INT-577：合并方式快捷筛选（whole|picked；后端映射为 merged/cherry_pick 布尔）
  if (query.mergeType !== undefined) dto.merge_type = query.mergeType
  // INT-577：合并容器统计块（后端 TaskListQuery.stats）
  if (query.stats !== undefined) dto.stats = query.stats
  // INT-301 F1：执行状态过滤（复用派生口径，徽章与筛选一致）
  if (query.executionStatus !== undefined) dto.execution_status = query.executionStatus
  // INT-423/467：可见性过滤（同名透传；后端 TaskListQuery.visibility）
  if (query.visibility !== undefined) dto.visibility = query.visibility
  // INT-273：派生任务类型过滤
  if (query.taskType !== undefined) dto.task_type = query.taskType
  return dto
}

/** HTTP 精简进度 → Socket 完整 ReadModel（计数字段映射 + 空集合填充） */
function fromHttpToFullProgress(raw: TaskProgressHttpDto): TaskProgress {
  const http = toTaskProgressHttp(raw);
  const currentCase = http.currentCase
    ? {
        caseId: http.currentCase.caseId,
        name: http.currentCase.name,
        step: http.currentCase.step,
        startTime: http.currentCase.startedAt ? Date.parse(http.currentCase.startedAt) : Date.now(),
      }
    : null;
  return {
    taskId: http.taskId,
    status: http.status,
    executionStatus: http.executionStatus,
    evaluationStatus: http.evaluationStatus,
    totalProgress: http.progress,
    completedCount: http.completedCases,
    inProgressCount: 0,
    executionFailedCount: http.failedCases,
    evaluationFailedCount: 0,
    totalCount: http.totalCases,
    currentCase,
    testCases: [],
    logs: [],
    apiResources: [],
    expectedTotalTime: null,
    expectedCompleteTime: null,
    // HTTP 轮询通道无已用时长字段；置空避免覆盖本地计时/最近一次 Socket 值
    usedTime: '',
  };
}

export const tasksApi = {
  /** 分页任务列表 → Paginated<Task>（入参 camelCase，snake_case 化在内部完成；INT-577 stats 块透传） */
  async getAll(params: TaskListQuery = {}, options: RequestOptions = {}) {
    const dto = await request<PaginatedDto<TaskDto> & { stats?: TaskContainerStatsDto } | TaskDto[]>('GET', '/tasks', null, { ...options, params: toTaskListQueryDto(params) });
    if (Array.isArray(dto)) {
      return { items: toTaskList(dto), total: dto.length, page: 1, perPage: dto.length, pages: 1, stats: null };
    }
    return { ...toPaginated(dto, toTask), stats: toContainerStats(dto.stats) };
  },

  /** 单个任务 → Task（TaskDetailData，含 cases） */
  async getOne(id: string | number): Promise<Task> {
    const dto = await request<TaskDetailDto>('GET', `/tasks/${id}`);
    return toTask(dto);
  },

  /**
   * 任务进度 → TaskProgress（camelCase ReadModel）。
   * 当前实现：网关返回 TaskProgressData（HTTP 精简形状），经 toTaskProgressHttp 后
   * 映射为 Socket 通道完整 ReadModel（testCases/logs/apiResources 为空）。
   * 若后端补齐 Socket 形状，改用 toTaskProgress 即可。
   */
  async getProgress(id: string | number): Promise<TaskProgress> {
    const raw = await request<TaskProgressHttpDto>('GET', `/tasks/${id}/progress`);
    return fromHttpToFullProgress(raw);
  },

  /** 用例详情 → CaseDetail（camelCase ReadModel） */
  async getCaseDetail(taskId: string | number, caseId: string | number): Promise<CaseDetail> {
    const dto = await request<Record<string, unknown>>('GET', `/tasks/${taskId}/cases/${caseId}/detail`);
    return toCaseDetail(dto);
  },

  /** 用例结果集 → CaseResults（camelCase ReadModel） */
  async getCaseResults(taskId: string | number, caseId: string | number): Promise<CaseResults> {
    const dto = await request<Record<string, unknown>>('GET', `/tasks/${taskId}/cases/${caseId}/results`);
    return toCaseResults(dto);
  },

  /** 创建任务：Domain 草稿 → TaskCreateRequest（snake_case 请求体） */
  async create(draft: TaskCreateDraft | Record<string, any>) {
    const body = (draft as TaskCreateDraft).caseIds !== undefined
      ? toTaskCreateDto(draft as TaskCreateDraft)
      : draft; // 兼容旧调用（直接传请求体）
    return request('POST', '/tasks', body);
  },

  /** 启动任务 → TaskStartResult（camelCase） */
  async start(id: string | number) {
    const raw = await request<Parameters<typeof toTaskStartResult>[0]>('POST', `/tasks/${id}/start`);
    return toTaskStartResult(raw);
  },

  async stop(id: string | number) {
    return request('POST', `/tasks/${id}/stop`);
  },

  async control(id: string | number, action: string) {
    return request('POST', `/tasks/${id}/control`, { action });
  },

  async delete(id: string | number) {
    return request('DELETE', `/tasks/${id}`);
  },

  async getStats(id: string | number) {
    return request('GET', `/tasks/${id}/stats`);
  },

  /** 任务域全量聚合统计（INT-200：统计卡与图表数据源，与列表筛选/分页无关） */
  async getDomainStats(granularity: string = 'day'): Promise<TaskDomainStats> {
    const dto = await request<TaskDomainStatsDto>('GET', '/tasks/stats', null, { params: { granularity } });
    return toTaskDomainStats(dto);
  },

  /** 批量操作：显式 task_ids（TaskBatchActionRequest） */
  async batchAction(action: string, ids: (string | number)[]) {
    const body: TaskBatchActionDto = { action, task_ids: ids };
    return request('POST', '/tasks/batch-action', body);
  },

  /** 合并任务：显式 task_ids（TaskMergeRequest） */
  async mergeTasks(ids: (string | number)[]) {
    const body: TaskMergeDto = { task_ids: ids };
    return request('POST', '/tasks/merge', body);
  },

  /** 动态调整用例：显式 case_ids（TaskUpdateCasesRequest） */
  async updateCases(id: string | number, action: string, caseIds: (string | number)[]) {
    const body: TaskUpdateCasesRequestDto = { action, case_ids: caseIds };
    return request('PATCH', `/tasks/${id}/cases`, body);
  },

  /** 重试任务：retryOptions 可选承载按用例选择（INT-302；缺省整任务语义） */
  async retry(id: string | number, retryOptions?: {
    caseIds?: (string | number)[]
    mode?: 'selected' | 'failed_only' | 'all'
  }) {
    return request('POST', `/tasks/${id}/retry`, {
      case_ids: retryOptions?.caseIds,
      mode: retryOptions?.mode,
    });
  },

  /** 移除任务用例（INT-305：执行详情模态窗删除用例，四阶段全允许） */
  async removeCase(taskId: string | number, caseId: string | number): Promise<TaskCaseRemoveResult> {
    const raw = await request<Record<string, unknown>>('DELETE', `/tasks/${taskId}/cases/${caseId}`);
    return toTaskCaseRemoveResult(raw);
  },

  /** 重新评估：显式 task_id（TaskReevaluateInput）；selection 可选按用例+按维度（INT-302） */
  async reevaluate(id: string | number, reevaluateType: string = 'all', reextractDeviceOutput: boolean = false, selection?: {
    caseIds?: (string | number)[]
    dimensionIds?: number[]
    mode?: 'selected' | 'failed_only' | 'all'
  }) {
    return request('POST', '/evaluation/task/reevaluate', {
      task_id: id,
      reevaluate_type: reevaluateType,
      reextract_device_output: reextractDeviceOutput,
      case_ids: selection?.caseIds,
      dimension_ids: selection?.dimensionIds,
      mode: selection?.mode,
    });
  },

  async update(id: string | number, taskData: { name?: string; description?: string }) {
    return request('PUT', `/tasks/${id}`, taskData);
  },

  /** 切换任务可见性（INT-423/467：PATCH /{id}/visibility，需 task:share + owner 校验） */
  async updateVisibility(id: string | number, visibility: string) {
    return request('PATCH', `/tasks/${id}/visibility`, { visibility });
  },

  /** 人工复核提交（INT-340）：result_ids + execution_status/evaluation_status + comment（备注必填） */
  async reviewResults(resultIds: (string | number)[], payload: {
    executionStatus?: string
    evaluationStatus?: string
    comment: string
  }) {
    return request('POST', '/tasks/results/review', {
      result_ids: resultIds,
      execution_status: payload.executionStatus,
      evaluation_status: payload.evaluationStatus,
      comment: payload.comment,
    });
  },

  /** 覆盖提醒计数（INT-340）：任务下已复核结果条数 */
  async getReviewCount(taskId: string | number): Promise<number> {
    const raw = await request<{ review_count?: number }>('GET', `/tasks/results/${taskId}/review-count`);
    return raw?.review_count ?? 0;
  },

  /** 复核历史（INT-340）：多次复核追加不覆盖 */
  async getReviewHistory(taskId: string | number): Promise<ReviewHistoryItem[]> {
    const raw = await request<{ items?: ReviewHistoryItem[] }>('GET', `/tasks/results/${taskId}/review-history`);
    return raw?.items ?? [];
  }
};
