/**
 * 映射视图交互状态（搜索关键词 / 转换筛选 / 平铺-分组视图 / 分页 / 分组折叠）。
 * 算法编辑模态窗与设备弹窗的映射表共用同一套视图状态语义。
 */
import { useEffect, useState } from 'react'

export function useMappingViewState<T extends string>(defaultView: T) {
  const [keyword, setKeyword] = useState('')
  const [transformFilter, setTransformFilter] = useState('all')
  const [viewMode, setViewMode] = useState<T>(defaultView)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  // 过滤条件/视图切换回到第一页
  useEffect(() => {
    setPage(1)
  }, [keyword, transformFilter, viewMode])

  const toggleCollapsed = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return {
    keyword,
    setKeyword,
    transformFilter,
    setTransformFilter,
    viewMode,
    setViewMode,
    page,
    setPage,
    pageSize,
    setPageSize,
    collapsed,
    toggleCollapsed,
  }
}
