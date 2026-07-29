/**
 * Tasks API module
 */
import { request, type RequestOptions } from './http';

export const tasksApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/tasks', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/tasks/${id}`);
  },

  async getProgress(id: string | number) {
    return request('GET', `/tasks/${id}/progress`);
  },

  async getCaseDetail(taskId: string | number, caseId: string | number) {
    return request('GET', `/tasks/${taskId}/cases/${caseId}/detail`);
  },

  async getCaseResults(taskId: string | number, caseId: string | number) {
    return request('GET', `/tasks/${taskId}/cases/${caseId}/results`);
  },

  async create(taskData: any) {
    return request('POST', '/tasks', taskData);
  },

  async start(id: string | number) {
    return request('POST', `/tasks/${id}/start`);
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

  async batchAction(action: string, ids: (string | number)[]) {
    return request('POST', '/tasks/batch-action', { action, taskIds: ids });
  },

  async mergeTasks(ids: (string | number)[]) {
    return request('POST', '/tasks/merge', { taskIds: ids });
  },

  async updateCases(id: string | number, action: string, caseIds: (string | number)[]) {
    return request('PATCH', `/tasks/${id}/cases`, { action, caseIds: caseIds });
  },

  async retry(id: string | number) {
    return request('POST', `/tasks/${id}/retry`);
  },

  async reevaluate(id: string | number, reevaluateType: string = 'all', reextractDeviceOutput: boolean = false) {
    return request('POST', `/evaluation/task/reevaluate`, { taskId: id, reevaluateType, reextractDeviceOutput });
  },

  async update(id: string | number, taskData: { name?: string; description?: string }) {
    return request('PUT', `/tasks/${id}`, taskData);
  }
};
