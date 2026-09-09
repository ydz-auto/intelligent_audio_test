/**
 * Test cases API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 */
import type { PaginatedResult } from '../../domain';
import { request, type RequestOptions } from '../http/client';
import { toTestCase, toTagViewItem } from '../adapters/testCaseAdapter';
import { toPaginated } from '../adapters/commonAdapter';
import { ViewMode } from '../../domain/enums';
import type { TagViewItemDto, TestCaseDto, TestCaseGroupDto, PaginatedDto } from '../dto';
import type { TestCase, TestCaseGroup, TagViewItem } from '../../domain/model/testCase';

/**
 * camelCase 查询参数 → snake_case 映射表
 * Infrastructure 层独占：将 store 传入的 camelCase key 转为后端期望的 snake_case 查询串
 */
const QUERY_PARAM_MAP: Record<string, string> = {
  algorithmType: 'algorithm_type',
  dimensionId: 'dimension_id',
  groupId: 'group_id',
  includeDeleted: 'include_deleted',
  testType: 'type',
};

/** 将 camelCase 参数对象转为后端期望的 snake_case 查询参数 */
function toQueryParams(params: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {};
  for (const [key, value] of Object.entries(params)) {
    const snakeKey = QUERY_PARAM_MAP[key] ?? key;
    if (value !== undefined && value !== null) {
      result[snakeKey] = value;
    }
  }
  return result;
}

/** 批量操作参数的 camelCase → snake_case 顶层 key 映射（值内 Dict 为动态结构，原样透传） */
const BATCH_ACTION_KEY_MAP: Record<string, string> = {
  algorithmParams: 'algorithm_params',
  playbackDevices: 'playback_devices',
  noiseAudioId: 'noise_audio_id',
  noiseSpl: 'noise_spl',
  noiseDeviceIds: 'noise_device_ids',
  targetGroupId: 'target_group_id',
  roundMode: 'round_mode',
  roundNumbers: 'round_numbers',
  roundDimensions: 'round_dimensions',
  multiDimensions: 'multi_dimensions',
  oldTagName: 'old_tag_name',
  newTagName: 'new_tag_name',
  testType: 'test_type',
  groupName: 'group_name',
  tagName: 'tag_name',
  copyToNewGroup: 'copy_to_new_group',
};

/** 批量操作请求体：浅层显式映射上行为 snake_case（Infrastructure 独占），未识别 key 原样透传 */
function toBatchActionDto(action: string, ids: (string | number)[], extraParams: Record<string, any>): Record<string, any> {
  const body: Record<string, any> = { action, ids };
  for (const [key, value] of Object.entries(extraParams)) {
    const snakeKey = BATCH_ACTION_KEY_MAP[key] ?? key;
    if (value !== undefined && value !== null) {
      body[snakeKey] = value;
    }
  }
  return body;
}

export const testcasesApi = {
  /** 分页用例列表 → PaginatedResult<TestCase>（camelCase） */
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}): Promise<PaginatedResult<TestCase>> {
    const queryParams = toQueryParams(params);
    const dto = await request<PaginatedDto<TestCaseDto>>('GET', '/testcases', null, { ...options, params: queryParams });
    const domain = toPaginated(dto, toTestCase);
    return { items: domain.items, total: domain.total, page: domain.page, perPage: domain.perPage, pages: domain.pages };
  },

  /**
   * 标签视图分页 → PaginatedResult<TagViewItem>（camelCase）。
   * 后端 view=tag 返回 {items: [{tag, testCases}]}，testCases 内层为 camelCase 用例行，
   * 与普通列表（snake_case）结构不同，故走独立 adapter 而非 getAll。
   */
  async getTagView(params: Record<string, any> = {}, options: RequestOptions = {}): Promise<PaginatedResult<TagViewItem>> {
    const queryParams = toQueryParams({ ...params, view: ViewMode.TAG });
    const dto = await request<PaginatedDto<TagViewItemDto>>('GET', '/testcases', null, { ...options, params: queryParams });
    const domain = toPaginated(dto, toTagViewItem);
    return { items: domain.items, total: domain.total, page: domain.page, perPage: domain.perPage, pages: domain.pages };
  },

  /** 单个用例 → TestCase */
  async getOne(id: string | number): Promise<TestCase> {
    const dto = await request<TestCaseDto>('GET', `/testcases/${id}`);
    return toTestCase(dto);
  },

  async create(tcData: Record<string, any> | FormData) {
    return request<TestCaseDto>('POST', '/testcases', tcData);
  },

  async update(id: string | number, tcData: Record<string, any> | FormData) {
    return request<void>('PUT', `/testcases/${id}`, tcData);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/testcases/${id}`);
  },

  /** 复制用例 → TestCase（camelCase） */
  async copy(id: string | number): Promise<TestCase> {
    const dto = await request<TestCaseDto>('POST', `/testcases/${id}/copy`);
    return toTestCase(dto);
  },

  async preview(id: string | number, previewData: any = {}) {
    const raw = await request<any>('POST', `/testcases/${id}/preview`, previewData);
    return {
      ...raw,
      playbackMode: raw?.playbackMode ?? raw?.playback_mode,
      audioStreamUrls: raw?.audioStreamUrls ?? raw?.audio_stream_urls,
      audioStreamUrl: raw?.audioStreamUrl ?? raw?.audio_stream_url,
    };
  },

  async stopPreview(id: string | number) {
    return request<void>('POST', `/testcases/${id}/stop_preview`);
  },

  async batchAction(action: string, ids: (string | number)[], extraParams: Record<string, any> = {}) {
    const raw = await request<any>('POST', '/testcases/batch', toBatchActionDto(action, ids, extraParams));
    return {
      ...raw,
      updatedCount: raw?.updatedCount ?? raw?.updated_count ?? 0,
      failedCount: raw?.failedCount ?? raw?.failed_count ?? 0,
      refreshedTestCaseIds: raw?.refreshedTestCaseIds ?? raw?.refreshed_test_case_ids ?? [],
      taskId: raw?.taskId ?? raw?.task_id,
    };
  },

  /** 分组列表 → PaginatedResult<TestCaseGroup>（camelCase，复用 groupAdapter 转换） */
  async getGroups(params: Record<string, any> = {}, options: RequestOptions = {}): Promise<PaginatedResult<TestCaseGroup>> {
    const queryParams = toQueryParams(params);
    const dto = await request<PaginatedDto<TestCaseGroupDto & { test_case_count?: number }>>('GET', '/groups', null, { ...options, params: queryParams });
    const domain = toPaginated(dto, toTestCaseGroup);
    return { items: domain.items, total: domain.total, page: domain.page, perPage: domain.perPage, pages: domain.pages };
  },

  async getTags() {
    return request<string[]>('GET', '/testcases/tags');
  },

  async export(ids: (string | number)[], format: string = 'json', includeDeleted: boolean = false) {
    const options: RequestOptions = {};
    if (format === 'xlsx') {
      options.responseType = 'blob';
    }
    return request<any>('POST', '/testcases/export', { ids, format, include_deleted: includeDeleted }, options);
  },

  async importCases(fileData: FormData) {
    const raw = await request<any>('POST', '/testcases/import', fileData, { isMultipart: true });
    return {
      ...raw,
      importedCount: raw?.importedCount ?? raw?.imported_count ?? 0,
      updatedCount: raw?.updatedCount ?? raw?.updated_count ?? 0,
    };
  },

  async downloadTemplate() {
    const options: RequestOptions = {
      responseType: 'blob'
    };
    return request<any>('GET', '/testcases/template/download', null, options);
  },

  async previewImport(fileData: FormData) {
    return request<any>('POST', '/testcases/import/preview', fileData, { isMultipart: true });
  },

  async createGroup(groupData: Record<string, any>) {
    return request<TestCaseGroupDto>('POST', '/groups', groupData);
  },

  async updateGroup(id: string | number, groupData: Record<string, any>) {
    return request<void>('PUT', `/groups/${id}`, groupData);
  },

  async deleteGroup(id: string | number, cascade: boolean = true) {
    return request<void>('DELETE', `/groups/${id}?cascade=${cascade}`);
  },

  async getRefreshTaskStatus(taskId: string) {
    const raw = await request<any>('GET', `/testcases/refresh_task/${taskId}`);
    return {
      ...raw,
      taskId: raw?.taskId ?? raw?.task_id,
      startedAt: raw?.startedAt ?? raw?.started_at,
      completedAt: raw?.completedAt ?? raw?.completed_at,
      failedCases: raw?.failedCases ?? raw?.failed_cases,
    };
  },

  async getIdsByFilter(filters: Record<string, any> = {}) {
    const queryFilters = toQueryParams(filters);
    return request<{ ids: (string | number)[] }>('POST', '/testcases/ids', queryFilters);
  }
};

/** 分组 DTO → TestCaseGroup（显式逐字段映射） */
function toTestCaseGroup(raw: TestCaseGroupDto & { test_case_count?: number }): TestCaseGroup {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description ?? undefined,
    algorithmType: raw.algorithm_type ?? undefined,
    createdAt: raw.created_at ?? undefined,
    updatedAt: raw.updated_at ?? undefined,
    testCaseCount: raw.test_case_count,
  };
}
