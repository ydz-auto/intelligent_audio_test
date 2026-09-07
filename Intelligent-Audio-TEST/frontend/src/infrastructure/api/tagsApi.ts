/**
 * Tags API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 查询参数/请求体显式 snake_case（per_page/category_id/tag_ids 等）。
 */
import { request, type RequestOptions } from '../http/client';
import {
  toTagCategory,
  toTagItem,
  toTagCategoryList,
  toTagList,
  toTagNameList,
  toTagsByCategoryList,
  toTagCategoryUpsertDto,
  toTagUpsertDto,
  toTagBatchCategoryDto,
} from '../adapters/tagAdapter';
import type {
  TagCategoryDto,
  TagItemDto,
  TagCategoryListDto,
  TagListDto,
  TagNameListDto,
  TagsByCategoryListDto,
} from '../dto/tagDto';
import type {
  Tag,
  TagItem,
  TagCategory,
  TagCategoryList,
  TagList,
  TagNameList,
  TagsByCategoryList,
  TagCategoryDraft,
  TagDraft,
  TagListQuery,
} from '../../domain/model/tag';

/** 标签域查询参数 → snake_case query（分类与标签共用 page/per_page/keyword；标签额外支持 category_id） */
function toCategoryQueryDto(query: TagListQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.page !== undefined) params.page = query.page;
  if (query.perPage !== undefined) params.per_page = query.perPage;
  if (query.keyword) params.keyword = query.keyword;
  // 后端 TagListQuery 支持 category_id 过滤（GET /tags）
  if (query.categoryId !== undefined) params.category_id = query.categoryId;
  return params;
}

export const tagsApi = {
  /** 分类列表（非分页结构：items + total） */
  async getCategories(params: TagListQuery = {}, options: RequestOptions = {}): Promise<TagCategoryList> {
    const dto = await request<TagCategoryListDto>('GET', '/tags/categories', null, {
      ...options,
      params: toCategoryQueryDto(params),
    });
    return toTagCategoryList(dto);
  },

  async getCategory(id: number, options: RequestOptions = {}): Promise<TagCategory> {
    const dto = await request<TagCategoryDto>('GET', `/tags/categories/${id}`, null, options);
    return toTagCategory(dto);
  },

  /** 创建分类：camelCase → snake_case 请求体 */
  async createCategory(data: TagCategoryDraft, options: RequestOptions = {}): Promise<TagCategory> {
    const dto = await request<TagCategoryDto>('POST', '/tags/categories', toTagCategoryUpsertDto(data), options);
    return toTagCategory(dto);
  },

  async updateCategory(id: number, data: TagCategoryDraft, options: RequestOptions = {}): Promise<TagCategory> {
    const dto = await request<TagCategoryDto>('PUT', `/tags/categories/${id}`, toTagCategoryUpsertDto(data), options);
    return toTagCategory(dto);
  },

  async deleteCategory(id: number, options: RequestOptions = {}) {
    return request<void>('DELETE', `/tags/categories/${id}`, null, options);
  },

  /** 标签列表（非分页结构：items + total；可按分类过滤） */
  async getTags(params: TagListQuery = {}, options: RequestOptions = {}): Promise<TagList> {
    const dto = await request<TagListDto>('GET', '/tags', null, {
      ...options,
      params: toCategoryQueryDto(params),
    });
    return toTagList(dto);
  },

  /** 标签名列表（items 为字符串数组） */
  async getTagNames(params: TagListQuery = {}, options: RequestOptions = {}): Promise<TagNameList> {
    const dto = await request<TagNameListDto>(
      'GET', '/tags/names', null, { ...options, params: toCategoryQueryDto(params) }
    );
    return toTagNameList(dto);
  },

  /** 按分类分组的标签 */
  async getTagsByCategory(options: RequestOptions = {}): Promise<TagsByCategoryList> {
    const dto = await request<TagsByCategoryListDto>('GET', '/tags/by-category', null, options);
    return toTagsByCategoryList(dto);
  },

  async getTag(id: number, options: RequestOptions = {}): Promise<TagItem> {
    const dto = await request<TagItemDto>('GET', `/tags/${id}`, null, options);
    return toTagItem(dto);
  },

  /** 创建标签：camelCase → snake_case 请求体 */
  async createTag(data: TagDraft, options: RequestOptions = {}): Promise<TagItem> {
    const dto = await request<TagItemDto>('POST', '/tags', toTagUpsertDto(data), options);
    return toTagItem(dto);
  },

  async updateTag(id: number, data: TagDraft, options: RequestOptions = {}): Promise<TagItem> {
    const dto = await request<TagItemDto>('PUT', `/tags/${id}`, toTagUpsertDto(data), options);
    return toTagItem(dto);
  },

  /** 删除标签；cascade=true 时级联删除标签及其下所有测试用例 */
  async deleteTag(id: number, cascade = false, options: RequestOptions = {}) {
    return request<void>('DELETE', `/tags/${id}`, null, {
      ...options,
      params: { ...(options.params as Record<string, string | number> | undefined), cascade: cascade ? 'true' : 'false' },
    });
  },

  /** 批量移动标签到分类（请求体 tag_ids/category_id） */
  async batchUpdateCategory(tagIds: number[], categoryId: number | null, options: RequestOptions = {}) {
    return request<void>('PUT', '/tags/batch-category', toTagBatchCategoryDto(tagIds, categoryId), options);
  }
};

// re-export 供类型消费方使用（保持 tagsApi 单一出口）
export type { Tag };
