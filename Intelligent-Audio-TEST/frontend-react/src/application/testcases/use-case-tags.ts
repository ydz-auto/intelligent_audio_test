/**
 * 标签/分类 query（application 层，11_用例域.md §4.3 三页口径联动）。
 * queryKey ['tags','items'] / ['tags','categories'] 供用例管理页标签 facet（按分类呈现）、
 * 行标签 Badge（名称→分类/色值登记表）共享；标签改名后 queryKey 失效自动刷新。
 */
import { useQuery } from '@tanstack/react-query'

import {
  fetchTagCategories,
  fetchTags,
} from '@/infrastructure/api/tags-api'

export function useCaseTags() {
  return useQuery({
    queryKey: ['tags', 'items'],
    queryFn: fetchTags,
    staleTime: 30_000,
  })
}

export function useTagCategories() {
  return useQuery({
    queryKey: ['tags', 'categories'],
    queryFn: fetchTagCategories,
    staleTime: 30_000,
  })
}
