import { ref, computed, watch, type Ref } from 'vue'

/**
 * 通用分页 composable
 * 统一处理 totalPages 计算、slice 分页、页码导航
 *
 * 服务端分页场景：传 options.totalCount（后端返回的总条数 Ref）即可，
 * totalItems/totalPages 基于该值计算，sourceList 可不传（本地分页才需要）。
 */
export function usePagination<T>(
  sourceList?: Ref<T[]>,
  pageSize: Ref<number> = ref(10),
  options?: { currentPage?: Ref<number>; totalCount?: Ref<number> }
) {
  const currentPage = options?.currentPage ?? ref(1)
  const totalCountRef = options?.totalCount
  const totalItems = computed(() =>
    totalCountRef ? totalCountRef.value : (sourceList?.value.length ?? 0)
  )
  const totalPages = computed(() =>
    Math.max(1, Math.ceil(totalItems.value / pageSize.value))
  )

  const paginatedItems = computed(() => {
    if (!sourceList) return []
    const start = (currentPage.value - 1) * pageSize.value
    const end = start + pageSize.value
    return sourceList.value.slice(start, end)
  })

  function goToPage(page: number) {
    currentPage.value = Math.max(1, Math.min(page, totalPages.value))
  }
  function nextPage() { goToPage(currentPage.value + 1) }
  function prevPage() { goToPage(currentPage.value - 1) }
  function setPageSize(size: number) {
    pageSize.value = size
    goToPage(1)
  }

  // 总条数变化时重置到第一页（服务端分页时监听 totalCount，否则监听源列表长度）
  watch(() => (totalCountRef ? totalCountRef.value : (sourceList?.value.length ?? 0)), () => {
    if (currentPage.value > totalPages.value) {
      currentPage.value = 1
    }
  })

  return {
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    paginatedItems,
    goToPage,
    nextPage,
    prevPage,
    setPageSize,
  }
}
