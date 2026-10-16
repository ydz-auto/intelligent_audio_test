/**
 * 标签管理页 query（application 层，11_用例域.md §4.3 三页口径联动）。
 * queryKey 前缀 ['tags','categories'] / ['tags','items'] 与用例管理页共享——
 * 标签改名/分类增删后 invalidate(['tags']) 自动刷新三页；mock 桩见 infrastructure/api/tags-api.ts。
 * 搜索/分类过滤在本层做（mock 阶段不服务端分页，照 use-testcases-list 口径），
 * 接线后替换为 GET /tags/categories?keyword、GET /tags?category_id&keyword。
 */
import { useQuery } from '@tanstack/react-query'

import {
  fetchTagCategories,
  fetchTags,
} from '@/infrastructure/api/tags-api'

/** 全部分类（左分类树；keyword 过滤照 GET /tags/categories?keyword） */
export function useTagCategories(keyword?: string) {
  return useQuery({
    queryKey: ['tags', 'categories', keyword ?? ''],
    queryFn: async () => {
      const all = await fetchTagCategories()
      if (!keyword) return all
      const kw = keyword.trim()
      return all.filter(
        (c) =>
          c.name.toLowerCase().includes(kw) ||
          (c.description ?? '').toLowerCase().includes(kw)
      )
    },
    staleTime: 30_000,
  })
}

/**
 * 标签列表（右标签表；categoryId=null 即「未分类」视图——按现实现口径不按分类过滤，
 * 展示全量；keyword 过滤照 GET /tags?category_id&keyword）。
 */
export function useTags(categoryId: number | null, keyword?: string) {
  return useQuery({
    queryKey: ['tags', 'items', categoryId, keyword ?? ''],
    queryFn: async () => {
      const all = await fetchTags()
      let items = all
      if (categoryId !== null) items = items.filter((t) => t.categoryId === categoryId)
      if (keyword) {
        const kw = keyword.trim().toLowerCase()
        items = items.filter(
          (t) =>
            t.name.toLowerCase().includes(kw) ||
            (t.description ?? '').toLowerCase().includes(kw)
        )
      }
      return items
    },
    staleTime: 30_000,
  })
}
