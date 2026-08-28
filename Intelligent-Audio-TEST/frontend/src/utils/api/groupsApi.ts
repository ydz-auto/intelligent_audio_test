/**
 * Groups API module
 */
import { request } from './http';

export const groupsApi = {
  async getAll(params: Record<string, any> = {}) {
    const query = new URLSearchParams();
    if (params.page) query.append('page', String(params.page));
    if (params.per_page) query.append('per_page', String(params.per_page));
    if (params.perPage) query.append('per_page', String(params.perPage));
    if (params.algorithm_type) query.append('algorithm_type', params.algorithm_type);
    if (params.algorithmType) query.append('algorithm_type', params.algorithmType);
    if (params.keyword) query.append('keyword', params.keyword);
    if (params.type) query.append('type', params.type);
    if (params.dimension_id) query.append('dimension_id', String(params.dimension_id));
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
