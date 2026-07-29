/**
 * APIs (external API services) API module
 */
import { request, type RequestOptions } from './http';

export const apisApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/apis', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/apis/${id}`);
  },

  async create(apiData: any, options: RequestOptions = {}) {
    return request('POST', '/apis', apiData, options);
  },

  async update(id: string | number, apiData: any, options: RequestOptions = {}) {
    return request('PUT', `/apis/${id}`, apiData, options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/apis/${id}`);
  },

  async healthCheck(id: string | number) {
    return request('POST', `/apis/${id}/health`);
  },

  async testConnection(id: string | number) {
    return request('POST', `/apis/${id}/health`);
  },

  async stopTest(id: string | number) {
    return request('POST', `/apis/${id}/stop-test`);
  }
};
