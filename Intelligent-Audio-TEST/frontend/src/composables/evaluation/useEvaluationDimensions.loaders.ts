/**
 * useEvaluationDimensions —— 数据加载与分页过滤
 *
 * 负责从后端拉取维度/分类/算法列表（fetchData），及由筛选/分页状态驱动的重新拉取函数。
 */
import { evaluationPort } from './evaluationPort';
import { algorithmPort } from '../algorithm/algorithmPort';
import type { EvalDimensionState } from './useEvaluationDimensions.state';

/** 创建数据加载与分页过滤模块 */
export function createEvalDimensionLoaders(state: EvalDimensionState) {
  const {
    loading,
    error,
    searchKeyword,
    filterStatus,
    filterCategory,
    currentPage,
    pageSize,
    dimensions,
    categories,
    algorithms,
    totalItems,
    totalPages,
  } = state;

  // ========== 数据获取 ==========
  async function fetchData() {
    loading.value = true;
    error.value = null;
    try {
      const params: Record<string, any> = { page: currentPage.value, perPage: pageSize.value, search: searchKeyword.value };

      if (filterStatus.value !== 'all') {
        params.status = filterStatus.value === 'active';
      }

      if (filterCategory.value !== 'all') {
        params.categoryId = filterCategory.value;
      }

      const [dimsData, catsData, algosData] = await Promise.all([
        evaluationPort.getAll(params),
        evaluationPort.getCategories(),
        algorithmPort.getOptions()
      ]);

      dimensions.value = dimsData?.items || [];
      totalItems.value = dimsData?.total || 0;
      totalPages.value = dimsData?.pages || 0;
      categories.value = catsData?.items || [];
      algorithms.value = (algosData?.algorithms || []).map((algo: any) => ({
        value: algo.value,
        label: algo.name || algo.value
      }));
    } catch (err) {
      console.error('Failed to fetch evaluation data:', err);
      error.value = '获取评估维度失败';
    } finally {
      loading.value = false;
    }
  }

  // ========== 分页与过滤 ==========
  // 注：此处分页导航函数需在页码变更后触发 fetchData() 拉取服务端数据，
  // 与 usePagination 的纯客户端导航语义不同，因此保留手写实现。
  function goToPage(page: number) {
    if (page >= 1 && page <= totalPages.value) {
      currentPage.value = page;
      fetchData();
    }
  }

  function prevPage() {
    if (currentPage.value > 1) {
      currentPage.value--;
      fetchData();
    }
  }

  function nextPage() {
    if (currentPage.value < totalPages.value) {
      currentPage.value++;
      fetchData();
    }
  }

  function onPageSizeChange(size: number) {
    pageSize.value = size;
    currentPage.value = 1;
    fetchData();
  }

  function searchDimensions() {
    currentPage.value = 1;
    fetchData();
  }

  function filterDimensions() {
    currentPage.value = 1;
    fetchData();
  }

  function resetFilters() {
    searchKeyword.value = '';
    filterStatus.value = 'all';
    filterCategory.value = 'all';
    currentPage.value = 1;
    fetchData();
  }

  return {
    fetchData,
    goToPage,
    prevPage,
    nextPage,
    onPageSizeChange,
    searchDimensions,
    filterDimensions,
    resetFilters,
  };
}

/** 数据加载与分页过滤模块类型（由工厂推断） */
export type EvalDimensionLoadersModule = ReturnType<typeof createEvalDimensionLoaders>;