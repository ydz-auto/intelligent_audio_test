/**
 * useEvaluationDimensions —— 数据加载与过滤
 *
 * 负责从后端拉取维度/分类/算法列表（fetchData），及搜索/筛选状态的重置函数。
 *
 * INT-281：维度列表恢复全量拉取 + 前端过滤（对齐 V9.7.10 基线口径）。
 * 主/子维度必须同屏聚合展示，服务端分页会把父子切到不同页；搜索/状态/分类/
 * 算法筛选由 state.ts 的 filteredDimensions 计算属性在前端联动（含主/子联动整组展示）。
 * 维度量级小（当前 10 条），评估维度超过千条前无需服务端分页。
 */
import { evaluationPort } from './evaluationPort';
import { algorithmPort } from '../algorithm/algorithmPort';
import { DIMENSION_FETCH_ALL_PER_PAGE } from './useEvaluationDimensions.constants';
import type { EvalDimensionState } from './useEvaluationDimensions.state';

/** 创建数据加载与过滤模块 */
export function createEvalDimensionLoaders(state: EvalDimensionState) {
  const {
    loading,
    error,
    searchKeyword,
    filterStatus,
    filterCategory,
    filterAlgorithm,
    dimensions,
    categories,
    algorithms,
  } = state;

  // ========== 数据获取 ==========
  async function fetchData() {
    loading.value = true;
    error.value = null;
    try {
      // 一次拉全量，搜索/筛选改为前端过滤，保证主/子维度始终同屏聚合展示（对齐 V9.7.10）
      // INT-467 例外口径：可见性筛选同样在前端派生（state.filteredDimensions），不传
      // `?visibility=` 服务端过滤——服务端 ACL 仍只返回当前用户可见集（INT-465），
      // 前端 chips 在可见集内做父/子联动的二次过滤，二者功能等价且不破坏同屏聚合。
      const params: Record<string, any> = { page: 1, perPage: DIMENSION_FETCH_ALL_PER_PAGE };

      const [dimsData, catsData, algosData] = await Promise.all([
        evaluationPort.getAll(params),
        evaluationPort.getCategories(),
        algorithmPort.getOptions()
      ]);

      dimensions.value = dimsData?.items || [];
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

  // ========== 过滤（全量已在前端，搜索/筛选由 filteredDimensions 计算属性联动） ==========
  function searchDimensions() {
    // 无需重新请求：过滤为纯前端派生
  }

  function filterDimensions() {
    // 无需重新请求：过滤为纯前端派生
  }

  function resetFilters() {
    searchKeyword.value = '';
    filterStatus.value = 'all';
    filterCategory.value = 'all';
    filterAlgorithm.value = 'all';
  }

  return {
    fetchData,
    searchDimensions,
    filterDimensions,
    resetFilters,
  };
}

/** 数据加载与过滤模块类型（由工厂推断） */
export type EvalDimensionLoadersModule = ReturnType<typeof createEvalDimensionLoaders>;
