/**
 * Evaluation API module
 */
import type {
  EvaluationDimension,
  EvaluationCategory,
  PaginatedResponse
} from '../../shared/types';
import { request, type RequestOptions } from './http';

export const evaluationApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<EvaluationDimension>>('GET', '/evaluation/dimensions', null, { ...options, params });
  },

  async getOptions(params: { algorithm_type?: string } = {}) {
    return request<{ dimensions: EvaluationDimension[] }>('GET', '/evaluation/dimensions/options', null, { params });
  },

  async getOne(id: string | number) {
    return request<EvaluationDimension>('GET', `/evaluation/dimensions/${id}`);
  },

  async create(dimData: Partial<EvaluationDimension>) {
    return request<EvaluationDimension>('POST', '/evaluation/dimensions', dimData);
  },

  async update(id: string | number, dimData: Partial<EvaluationDimension>) {
    return request<void>('PUT', `/evaluation/dimensions/${id}`, dimData);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/evaluation/dimensions/${id}`);
  },

  async healthCheck(id: string | number) {
    return request<any>('GET', `/evaluation/dimensions/${id}/health`);
  },

  async batchAction(action: string, ids: (string | number)[]) {
    return request<any>('POST', '/evaluation/dimensions/batch', { action, itemIds: ids });
  },

  async calculateScore(id: string | number, value: any) {
    return request<{ score: number }>('POST', `/evaluation/dimensions/${id}/calculate`, { value });
  },

  async import(formData: FormData, updateExisting: boolean = false) {
    formData.append('update_existing', updateExisting.toString());
    return request<any>('POST', '/evaluation/dimensions/import', formData, { isMultipart: true });
  },

  async export(format: 'json' | 'excel' = 'json', ids?: (string | number)[], options: RequestOptions = {}) {
    const params: any = { format };
    if (ids && ids.length > 0) {
      params.ids = ids.join(',');
    }
    return request<any>('GET', '/evaluation/dimensions/export', null, { ...options, params, responseType: 'blob' });
  },

  async getCategories() {
    return request<PaginatedResponse<EvaluationCategory>>('GET', '/evaluation/categories');
  },

  async createCategory(catData: Partial<EvaluationCategory>) {
    return request<EvaluationCategory>('POST', '/evaluation/categories', catData);
  },

  async updateCategory(id: string | number, catData: Partial<EvaluationCategory>) {
    return request<void>('PUT', `/evaluation/categories/${id}`, catData);
  },

  async deleteCategory(id: string | number) {
    return request<void>('DELETE', `/evaluation/categories/${id}`);
  }
};
