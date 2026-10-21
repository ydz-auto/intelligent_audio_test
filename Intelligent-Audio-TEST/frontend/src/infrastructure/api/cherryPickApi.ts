/**
 * 挑选合并 API module（INT-339）
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在本文件（adapters 内联——
 * 挑选合并响应结构与任务域差异大，独立内联转换避免 adapter 层过度抽象）。
 * 接口路径 /tasks/cherry-picks/** 为设计文档 §8 技术契约；页面文案一律中文。
 */
import { request, type RequestOptions } from '../http/client';

// ===== Domain 类型（camelCase）=====

/** 购物车条目（含溯源快照 + 失效标注） */
export interface PickCartItem {
  itemId: number
  resultId: number
  sourceTaskId: number
  sourceTaskName?: string | null
  sourceCaseId?: string | null
  sourceDeviceId?: number | null
  sourceApiId?: number | null
  /** INT-577 §11-5：来源结果类型快照（result_data 解析，缺省 default；购物车树分组到 result_type 级） */
  sourceResultType?: string | null
  /** INT-577 §11-5 可选：来源用例/设备名（缺名容错显示 ID） */
  sourceCaseName?: string | null
  sourceDeviceName?: string | null
  executionStatus?: string | null
  createdAt?: string | null
  /** 下单前校验：源结果已删除时 true（§10） */
  invalid?: boolean
}

/** 购物车分组（按来源任务） */
export interface PickCartGroup {
  sourceTaskId: number
  sourceTaskName: string
  items: PickCartItem[]
}

export interface PickCart {
  groups: PickCartGroup[]
  total: number
  invalidItemIds: number[]
}

/** 挑选候选行（跨任务结果挑选查询） */
export interface PickCandidate {
  resultId: number
  taskId: number
  taskName: string
  taskStatus: string
  caseId: string
  /** INT-577 §11-2：用例名（缺名显示 ID，容错口径） */
  caseName?: string | null
  /** INT-1130 §11-7：用例卡元信息（三视图/购物车分组·标签组织数据源，toCamel 自动转换） */
  tags?: string[]
  groupId?: string | null
  groupName?: string | null
  /** INT-1130 §11-7：用例时长（秒；同用例管理 total_duration 口径累加，无音频/无时长 null） */
  duration?: number | null
  /** INT-1130 §11-7：轮次数（config.rounds 轮次数，缺省 0） */
  rounds?: number | null
  deviceId?: number | null
  apiId?: number | null
  /** INT-577 §11-2：被测设备/API 名（TestResult 归属二选一，缺省 None） */
  deviceName?: string | null
  apiName?: string | null
  /** INT-577 §11-2：结果类型（result_data/result_data_path 解析，缺省 default） */
  resultType?: string | null
  algorithmType?: string | null
  executionStatus: string
  evaluated?: boolean
  createdAt?: string | null
}

export interface PickCandidatePage {
  items: PickCandidate[]
  total: number
  page: number
  perPage: number
}

/** 挑选集摘要 */
export interface PickSetSummary {
  setId: number
  name: string
  description?: string | null
  itemCount: number
  createdAt?: string | null
}

/** 合并预览统计 */
export interface PickPreview {
  totalResults: number
  invalidResultIds: number[]
  sourceTaskCount: number
  sourceTaskIds: number[]
  deviceIds: number[]
  deviceNames: string[]
  caseCount: number
  executionStatusCounts: Record<string, number>
  duplicates: Array<{ deviceId: number | null; caseId: string | null; count: number }>
  /** INT-401：所选来源任务的任务级配置是否不一致（跨任务合并提示） */
  configInconsistent?: boolean
  /** INT-401：不一致的配置字段名（algorithm_type/algorithm_params 等，供提示列出） */
  configFields?: string[]
}

/** 下单出口（枚举化，拒绝魔法字符串——与后端 CherryPickCheckoutAction 对齐） */
export type PickCheckoutAction = 'merge' | 'reexecute' | 'reevaluate'

/** 下单结果 */
export interface PickCheckoutResult {
  taskId?: number
  resultCount?: number
  caseCount?: number
  started?: boolean
  submittedTaskIds?: number[]
  failed?: Array<{ taskId: number; message: string }>
  cleared?: boolean
}

/** 溯源分组（GET /tasks/{id}/cherry-pick-source） */
export interface PickSourceGroup {
  sourceTaskId: number
  sourceTaskName: string
  results: Array<{
    id: number
    resultId: number
    sourceCaseId?: string | null
    missing?: boolean
  }>
}

export interface PickSource {
  taskId: number
  isCherryPick: boolean
  total: number
  groups: PickSourceGroup[]
}

/** 通用 snake_case → camelCase 键转换（深结构；值类型保持原样）。
 *  Infrastructure 独占转换层：后端信封 data 为 snake_case，出口契约 camelCase。 */
function toCamel<T>(value: unknown): T {
  if (Array.isArray(value)) return value.map((v) => toCamel<unknown>(v)) as unknown as T;
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      const camelKey = k.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
      out[camelKey] = toCamel<unknown>(v);
    }
    return out as T;
  }
  return value as T;
}

// ===== API =====

export const cherryPickApi = {
  /** 当前用户购物车（按来源任务分组 + 失效标注） */
  async getCart(options: RequestOptions = {}): Promise<PickCart> {
    return toCamel(await request<Record<string, unknown>>('GET', '/tasks/cherry-picks/cart', null, options));
  },

  /** 加入购物车（源结果 ID 集合；溯源快照由后端提取） */
  async addToCart(resultIds: number[], options: RequestOptions = {}):
    Promise<{ added: number[]; missing: number[]; duplicated: number[] }> {
    return toCamel(await request<Record<string, unknown>>(
      'POST', '/tasks/cherry-picks/cart/items', { result_ids: resultIds }, options));
  },

  /** 从购物车移除条目 */
  async removeFromCart(itemIds: number[], options: RequestOptions = {}) {
    return request<{ removed: number }>(
      'POST', '/tasks/cherry-picks/cart/items/remove', { item_ids: itemIds }, options);
  },

  /** 清空购物车 */
  async clearCart(options: RequestOptions = {}) {
    return request<{ removed: number }>(
      'DELETE', '/tasks/cherry-picks/cart/items', null, options);
  },

  /** 购物车另存为挑选集（DTO 经 toCamel 收敛：set_id→setId / item_count→itemCount，设计 §8 camelCase 边界） */
  async saveAsSet(name: string, description?: string, options: RequestOptions = {}):
    Promise<{ setId: number; name: string; itemCount: number }> {
    return toCamel(await request<Record<string, unknown>>(
      'POST', '/tasks/cherry-picks/cart/save-as-set',
      { name, description: description ?? '' }, options));
  },

  /** 挑选集列表 */
  async listSets(options: RequestOptions = {}): Promise<{ items: PickSetSummary[] }> {
    return toCamel(await request<Record<string, unknown>>('GET', '/tasks/cherry-picks/sets', null, options));
  },

  /** 挑选集详情 */
  async getSet(setId: number, options: RequestOptions = {}) {
    return request<Record<string, any>>(
      'GET', `/tasks/cherry-picks/sets/${setId}`, null, options);
  },

  /** 删除挑选集 */
  async deleteSet(setId: number, options: RequestOptions = {}) {
    return request<{ deleted: number }>(
      'DELETE', `/tasks/cherry-picks/sets/${setId}`, null, options);
  },

  /** 挑选集恢复进购物车 */
  async restoreSetToCart(setId: number, options: RequestOptions = {}):
    Promise<{ added: number[]; missing: number[]; duplicated: number[] }> {
    return toCamel(await request<Record<string, unknown>>(
      'POST', `/tasks/cherry-picks/sets/${setId}/to-cart`, null, options));
  },

  /** 跨任务挑选候选查询（多条件 AND，设备+用例为点名必支持项） */
  async listCandidates(query: {
    taskIds?: number[]
    deviceIds?: number[]
    caseIds?: string[]
    /** INT-401：用例关键字模糊搜索（命中用例名/用例ID，与 case_ids 精确 IN 语义区分） */
    caseKeyword?: string
    executionStatus?: string
    evaluationStatus?: string
    startDate?: string
    endDate?: string
    page?: number
    perPage?: number
  }, options: RequestOptions = {}): Promise<PickCandidatePage> {
    const params: Record<string, any> = {};
    if (query.taskIds?.length) params.task_ids = query.taskIds.join(',');
    if (query.deviceIds?.length) params.device_ids = query.deviceIds.join(',');
    if (query.caseIds?.length) params.case_ids = query.caseIds.join(',');
    if (query.caseKeyword) params.case_keyword = query.caseKeyword;
    if (query.executionStatus) params.execution_status = query.executionStatus;
    if (query.evaluationStatus) params.evaluation_status = query.evaluationStatus;
    if (query.startDate) params.start_date = query.startDate;
    if (query.endDate) params.end_date = query.endDate;
    if (query.page) params.page = query.page;
    if (query.perPage) params.per_page = query.perPage;
    return toCamel(await request<Record<string, unknown>>(
      'GET', '/tasks/cherry-picks/candidates', null, { ...options, params }));
  },

  /** INT-577 §11-4：全选当前筛选——返回当前筛选命中全部 result_id 集合（跨页全选语义） */
  async selectAllCandidates(query: {
    taskIds?: number[]
    deviceIds?: number[]
    caseIds?: string[]
    caseKeyword?: string
    executionStatus?: string
    evaluationStatus?: string
    startDate?: string
    endDate?: string
  }, options: RequestOptions = {}): Promise<{ resultIds: number[] }> {
    const body: Record<string, unknown> = {};
    if (query.taskIds?.length) body.task_ids = query.taskIds;
    if (query.deviceIds?.length) body.device_ids = query.deviceIds;
    if (query.caseIds?.length) body.case_ids = query.caseIds;
    if (query.caseKeyword) body.case_keyword = query.caseKeyword;
    if (query.executionStatus) body.execution_status = query.executionStatus;
    if (query.evaluationStatus) body.evaluation_status = query.evaluationStatus;
    if (query.startDate) body.start_date = query.startDate;
    if (query.endDate) body.end_date = query.endDate;
    return toCamel(await request<Record<string, unknown>>(
      'POST', '/tasks/cherry-picks/candidates/select-all', body, options));
  },

  /** 合并预览（下单前统计/失效校验） */
  async preview(options: RequestOptions = {}): Promise<PickPreview> {
    return toCamel(await request<Record<string, unknown>>('POST', '/tasks/cherry-picks/preview', null, options));
  },

  /** 下单（三出口：merge/reexecute/reevaluate，缺省 merge） */
  async checkout(payload: {
    action?: PickCheckoutAction
    name?: string
    description?: string
    algorithm_type?: string
    algorithm_params?: Record<string, any>
    config?: Record<string, any>
  }, options: RequestOptions = {}): Promise<PickCheckoutResult> {
    return toCamel(await request<Record<string, unknown>>(
      'POST', '/tasks/cherry-picks/cart/checkout', payload, options));
  },

  /** 挑选溯源（新任务各结果来源任务） */
  async getSource(taskId: number | string, options: RequestOptions = {}): Promise<PickSource> {
    return toCamel(await request<Record<string, unknown>>(
      'GET', `/tasks/cherry-picks/${taskId}/source`, null, options));
  },
};
