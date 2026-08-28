import { ref, computed, watch, type Ref } from 'vue'

/**
 * 通用分页 composable
 * 统一处理 totalPages 计算、slice 分页、页码导航
 */
export function usePagination<T>(
  sourceList: Ref<T[]>,
  pageSize: Ref<number> = ref(10),
  options?: { currentPage?: Ref<number> }
) {
  const currentPage = options?.currentPage ?? ref(1)
  const totalItems = computed(() => sourceList.value.length)
  const totalPages = computed(() =>
    Math.max(1, Math.ceil(totalItems.value / pageSize.value))
  )

  const paginatedItems = computed(() => {
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

  // 源列表变化时重置到第一页
  watch(() => sourceList.value.length, () => {
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
