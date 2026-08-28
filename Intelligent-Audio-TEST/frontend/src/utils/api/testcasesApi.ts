/**
 * Test cases API module
 */
import type {
  TestCase,
  TestCaseGroup,
  TestCaseFormData,
  GroupFormData,
  PaginatedResponse
} from '../../shared/types';
import { request, type RequestOptions } from './http';

export const testcasesApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<TestCase>>('GET', '/testcases', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request<TestCase>('GET', `/testcases/${id}`);
  },

  async create(tcData: TestCaseFormData | FormData | Record<string, any>) {
    return request<TestCase>('POST', '/testcases', tcData);
  },

  async update(id: string | number, tcData: TestCaseFormData | FormData | Record<string, any>) {
    return request<void>('PUT', `/testcases/${id}`, tcData);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/testcases/${id}`);
  },

  async copy(id: string | number) {
    return request<TestCase>('POST', `/testcases/${id}/copy`);
  },

  async preview(id: string | number, previewData: any = {}) {
    return request<any>('POST', `/testcases/${id}/preview`, previewData);
  },

  async stopPreview(id: string | number) {
    return request<void>('POST', `/testcases/${id}/stop_preview`);
  },

  async batchAction(action: string, ids: (string | number)[], extraParams: Record<string, any> = {}) {
    return request<any>('POST', '/testcases/batch', { action, ids, ...extraParams });
  },

  async getStats() {
    return request<any>('GET', '/testcases/stats');
  },

  async getGroups(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<TestCaseGroup>>('GET', '/groups', null, { ...options, params });
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
    return request<any>('POST', '/testcases/import', fileData, { isMultipart: true });
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

  async createGroup(groupData: GroupFormData) {
    return request<TestCaseGroup>('POST', '/groups', groupData);
  },

  async updateGroup(id: string | number, groupData: GroupFormData) {
    return request<void>('PUT', `/groups/${id}`, groupData);
  },

  async deleteGroup(id: string | number, cascade: boolean = true) {
    return request<void>('DELETE', `/groups/${id}?cascade=${cascade}`);
  },

  async getRefreshTaskStatus(taskId: string) {
    return request<any>('GET', `/testcases/refresh_task/${taskId}`);
  },

  async getIdsByFilter(filters: Record<string, any> = {}) {
    return request<{ ids: (string | number)[] }>('POST', '/testcases/ids', filters);
  }
};
