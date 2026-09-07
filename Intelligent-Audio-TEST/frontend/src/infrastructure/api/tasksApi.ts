/**
 * Tasks API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 */
import { request, type RequestOptions } from '../http/client';
import { toTask, toTaskList, toTaskCreateDto, toCaseDetail, toCaseResults } from '../adapters/taskAdapter';
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
} from '../dto';
import type { TaskProgressHttpDto } from '../dto/taskProgressDto';
import type { Task, TaskCreateDraft } from '../../domain/model/task';
import type { CaseDetail, CaseResults } from '../../domain/model/taskCaseDetail';
import type { TaskProgress } from '../../domain/model/taskProgress';

/** 任务列表查询参数（camelCase 域契约；snake_case 化在本文件内部完成） */
export interface TaskListQuery {
  page?: number
  perPage?: number
  status?: string
  type?: string
  algorithmType?: string
  search?: string
  startTime?: string
  endTime?: string
}

/** camelCase 任务查询 → snake_case HTTP query（后端 TaskListQueryDto 契约） */
function toTaskListQueryDto(query: TaskListQuery): TaskListQueryDto {
  const dto: TaskListQueryDto = { page: query.page ?? 1, per_page: query.perPage ?? 10 }
  if (query.status !== undefined) dto.status = query.status
  if (query.type !== undefined) dto.type = query.type
  if (query.algorithmType !== undefined) dto.algorithm_type = query.algorithmType
  if (query.search !== undefined) dto.search = query.search
  if (query.startTime !== undefined) dto.start_date = query.startTime
  if (query.endTime !== undefined) dto.end_date = query.endTime
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
    usedTime: '0分钟',
  };
}

export const tasksApi = {
  /** 分页任务列表 → Paginated<Task>（入参 camelCase，snake_case 化在内部完成） */
  async getAll(params: TaskListQuery = {}, options: RequestOptions = {}) {
    const dto = await request<PaginatedDto<TaskDto> | TaskDto[]>('GET', '/tasks', null, { ...options, params: toTaskListQueryDto(params) });
    if (Array.isArray(dto)) {
      return { items: toTaskList(dto), total: dto.length, page: 1, perPage: dto.length, pages: 1 };
    }
    return toPaginated(dto, toTask);
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

  async retry(id: string | number) {
    return request('POST', `/tasks/${id}/retry`);
  },

  /** 重新评估：显式 task_id（TaskReevaluateInput） */
  async reevaluate(id: string | number, reevaluateType: string = 'all', reextractDeviceOutput: boolean = false) {
    return request('POST', '/evaluation/task/reevaluate', {
      task_id: id,
      reevaluate_type: reevaluateType,
      reextract_device_output: reextractDeviceOutput,
    });
  },

  async update(id: string | number, taskData: { name?: string; description?: string }) {
    return request('PUT', `/tasks/${id}`, taskData);
  }
};
