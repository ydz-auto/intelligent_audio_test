/**
 * Logs API module
 */
import type {
  Log,
  LogQueryParams,
  PaginatedResponse
} from '../../shared/types';
import { request, type RequestOptions } from './http';

export const logsApi = {
  async getAll(params: LogQueryParams = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<Log>>('GET', '/logs', null, { ...options, params });
  },

  async getStats(params: LogQueryParams = {}, options: RequestOptions = {}) {
    return request<Record<string, number>>('GET', '/logs/stats', null, { ...options, params });
  },

  async mark(logIds: (string | number)[], mark: string = 'flagged') {
    return request('PUT', '/logs/mark', { logIds: logIds, mark });
  },

  async export(params: LogQueryParams = {}) {
    return request('GET', '/logs/export', params);
  },

  async clear(params: LogQueryParams = {}) {
    return request('POST', '/logs/clear', params);
  },

  async refresh(lastId: string | number) {
    return request('POST', '/logs/refresh', { lastId: lastId });
  }
};
