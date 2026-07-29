/**
 * Reports API module
 */
import type {
  Report,
  ReportListParams,
  PaginatedResponse
} from '../../shared/types';
import { request, apiBaseUrl, type RequestOptions } from './http';

export const reportsApi = {
  async getAll(params: Partial<ReportListParams> = {}, options: RequestOptions = {}): Promise<PaginatedResponse<Report>> {
    const defaultParams : ReportListParams = {page: 1, perPage: 10, sortBy: 'created_at', order: 'desc' as const};
    const mergedParams = {...defaultParams, ...params};
    return request<PaginatedResponse<Report>>('GET', '/reports', null, { ...options, params: mergedParams });
  },

  async getOne(id: string | number) {
    return request('GET', `/reports/${id}`);
  },

  async delete(id: string | number): Promise<void> {
    return request<void>('DELETE', `/reports/${id}`);
  },

  async batchDelete(ids: (string | number)[]): Promise<void> {
    return request<void>('POST', '/reports/batch-delete', { reportIds: ids });
  },

  async getProgress(id: string | number): Promise<any> {
    return request<any>('GET', `/reports/${id}/progress`);
  },

  async compare(taskIds: (string | number)[], name: string | null = null): Promise<{ id?: string | number; reportId?: string | number }> {
    return request<{ id?: string | number; reportId?: string | number }>('POST', '/reports/compare', { taskIds: taskIds, name });
  },

  async secondaryCompare(reportIds: (string | number)[]): Promise<{ reportKey: (string | number)[]; status: string }> {
    return request<{ reportKey: (string | number)[]; status: string }>('POST', '/reports/secondary-compare', { reportIds: reportIds });
  },

  async export(reportIds: (string | number)[], format: string = 'excel'): Promise<Blob> {
    return request<Blob>('POST', '/reports/export', { ids: reportIds, format }, { responseType: 'blob' });
  },

  async generateTaskReport(taskId: string | number, name: string | null = null) {
    return request('POST', '/reports/generate-task', { taskId: taskId, name });
  },

  async getTrendData(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/reports/trend', null, { ...options, params });
  },

  async getCaseAveragesByFilters(
    taskId: string | number,
    filters: Record<string, any> = {},
    options: RequestOptions = {}
  ) {
    return request('POST', '/reports/case-averages', { taskId, ...filters }, options);
  },

  async create(reportData: any) {
    return request('POST', '/reports', reportData);
  },

  async update(id: string | number, reportData: any) {
    return request('PUT', `/reports/${id}`, reportData);
  },

  async publish(id: string | number) {
    return request('POST', `/reports/${id}/publish`);
  },

  async getCases(id: string | number, params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', `/reports/${id}/cases`, null, { ...options, params });
  },

  async searchCases(id: string | number, body: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('POST', `/reports/${id}/cases/search`, body, options);
  },

  async downloadCaseLogs(reportId: string | number, caseId: string | number): Promise<Blob> {
    return request<Blob>('GET', `/reports/${reportId}/cases/${caseId}/logs/download`, null, { responseType: 'blob' });
  },

  getCaseLogsDownloadUrl(reportId: string | number, caseId: string | number): string {
    const base = apiBaseUrl.replace(/\/$/, '');
    return `${base}/reports/${reportId}/cases/${caseId}/logs/download`;
  }
};
