/**
 * Tags API module
 */
import type { TagCategory, TagItem } from '../../shared/types';
import { request } from './http';

export const tagsApi = {
  async getCategories(params: Record<string, any> = {}) {
    return request<{ items: TagCategory[]; total: number }>('GET', '/tags/categories', null, { params });
  },

  async getCategory(id: number) {
    return request<TagCategory>('GET', `/tags/categories/${id}`);
  },

  async createCategory(data: Partial<TagCategory>) {
    return request<TagCategory>('POST', '/tags/categories', data);
  },

  async updateCategory(id: number, data: Partial<TagCategory>) {
    return request<TagCategory>('PUT', `/tags/categories/${id}`, data);
  },

  async deleteCategory(id: number) {
    return request<void>('DELETE', `/tags/categories/${id}`);
  },

  async getTags(params: Record<string, any> = {}) {
    return request<{ items: TagItem[]; total: number }>('GET', '/tags', null, { params });
  },

  async getTagNames(params: Record<string, any> = {}) {
    return request<{ items: string[]; total: number }>('GET', '/tags/names', null, { params });
  },

  async getTagsByCategory() {
    return request<{ items: Array<{ category: TagCategory | null; tags: TagItem[] }>; total: number }>('GET', '/tags/by-category');
  },

  async getTag(id: number) {
    return request<TagItem>('GET', `/tags/${id}`);
  },

  async createTag(data: Partial<TagItem>) {
    return request<TagItem>('POST', '/tags', data);
  },

  async updateTag(id: number, data: Partial<TagItem>) {
    return request<TagItem>('PUT', `/tags/${id}`, data);
  },

  async deleteTag(id: number) {
    return request<void>('DELETE', `/tags/${id}`);
  },

  async batchUpdateCategory(tagIds: number[], categoryId: number | null) {
    return request<void>('PUT', '/tags/batch-category', { tag_ids: tagIds, category_id: categoryId });
  }
};
