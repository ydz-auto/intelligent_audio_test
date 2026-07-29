/**
 * Groups API module
 */
import { request } from './http';

export const groupsApi = {
  async getAll(params: { page?: number; perPage?: number; algorithmType?: string } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.append('page', String(params.page));
    if (params.perPage) query.append('per_page', String(params.perPage));
    if (params.algorithmType) query.append('algorithm_type', params.algorithmType);
    const queryString = query.toString();
    return request('get', `/groups${queryString ? '?' + queryString : ''}`);
  },

  async create(groupData: any) {
    return request('POST', '/groups', groupData);
  },

  async update(id: string | number, groupData: any) {
    return request('PUT', `/groups/${id}`, groupData);
  },

  async delete(id: string | number) {
    return request('DELETE', `/groups/${id}`);
  },

  async moveCases(sourceId: string | number, targetId: string | number, caseIds: (string | number)[]) {
    return request('POST', '/groups/move-cases', { sourceId: sourceId, targetId: targetId, caseIds: caseIds });
  }
};
