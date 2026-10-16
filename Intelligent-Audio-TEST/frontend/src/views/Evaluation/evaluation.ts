import { onMounted, onBeforeUnmount } from 'vue';
import { useEvaluationDimensions } from '../../composables/evaluation/useEvaluationDimensions';
import { useEvaluationCategories } from '../../composables/evaluation/useEvaluationCategories';
import { useEvaluationBatchOps } from '../../composables/evaluation/useEvaluationBatchOps';
import { useEvaluationImport } from '../../composables/evaluation/useEvaluationImport';
import { useEvaluationModals } from '../../composables/evaluation/useEvaluationModals';

/**
 * useEvaluation - 轻量级协调层
 *
 * 组合以下子模块，暴露统一接口给 Evaluation.vue 使用：
 * - useEvaluationDimensions: 维度管理（CRUD、批量选择、搜索/过滤、API健康检查、权重）
 * - useEvaluationCategories: 分类管理（CRUD、展开/折叠）
 * - useEvaluationBatchOps: 批量操作（batchEnable/batchDisable/batchDelete）与菜单 UI
 * - useEvaluationImport: 导入导出（import/export/handleImport）
 * - useEvaluationModals: 模态框管理（openEditModal/openAddModal/openAPISettingsModal 等）
 *
 * 该文件仅负责组合与状态重置协调，不包含具体业务逻辑。
 */
export function useEvaluation() {
  // ========== 组合子模块 ==========

  // 1. 维度模块（基础模块，持有 loading/dimensions/categories/algorithms/selectedDimensions 等核心状态）
  const dimensionsModule = useEvaluationDimensions();

  // 2. 分类模块（依赖维度模块的 loading/categories/fetchData）
  const categoriesModule = useEvaluationCategories(dimensionsModule);

  // 3. 批量操作模块（依赖维度模块的 loading/selectedDimensions/fetchData）
  const batchOpsModule = useEvaluationBatchOps(dimensionsModule);

  // 4. 导入导出模块（依赖维度模块的 loading/fetchData）
  const importModule = useEvaluationImport(dimensionsModule);

  // 5. 模态框模块（依赖维度模块的 dimensions/categories/evaluationFields/dimensionTemplate/saveDimension/loading，分类模块的 saveCategory）
  const modalsModule = useEvaluationModals(dimensionsModule, categoriesModule);

  // ========== 协调逻辑 ==========

  // 判断是否为 LLM Judge 维度
  function isLlmJudge(dimension: any) {
    return dimension.resultType === 'llm_judge';
  }

  // 生命周期：初始化与清理
  onMounted(() => {
    batchOpsModule.initEvaluation();
  });

  onBeforeUnmount(() => {
    batchOpsModule.cleanupEvaluation();
  });

  // 重置所有状态：跨模块重置
  function resetAllStates() {
    dimensionsModule.resetFilters();
    dimensionsModule.selectedDimensions.value = [];
    dimensionsModule.newDimension.value = { ...dimensionsModule.dimensionTemplate } as any;
    importModule.importSettings.value = { updateExisting: true, skipErrors: false };
    categoriesModule.newCategory.value = { name: '', description: '', icon: 'fas fa-tachometer-alt' };
  }

  // ========== 暴露统一接口（与原 useEvaluation 完全兼容） ==========

  return {
    // 基础状态（来自维度模块）
    loading: dimensionsModule.loading,
    error: dimensionsModule.error,

    // 数据获取（加载/错误态重试按钮使用）
    fetchData: dimensionsModule.fetchData,

    // UI 引用（来自批量操作模块）
    batchMenuRef: batchOpsModule.batchMenuRef,
    importExportMenuRef: batchOpsModule.importExportMenuRef,

    // 过滤状态（来自维度模块）
    searchKeyword: dimensionsModule.searchKeyword,
    filterStatus: dimensionsModule.filterStatus,
    filterCategory: dimensionsModule.filterCategory,
    filterAlgorithm: dimensionsModule.filterAlgorithm,
    filterVisibility: dimensionsModule.filterVisibility,
    selectedDimensions: dimensionsModule.selectedDimensions,

    // 视图模式（列表/分组，来自维度模块）
    viewMode: dimensionsModule.viewMode,
    isGroupExpanded: dimensionsModule.isGroupExpanded,
    toggleGroupExpanded: dimensionsModule.toggleGroupExpanded,

    // 数据列表（来自维度模块）
    categories: dimensionsModule.categories,
    algorithms: dimensionsModule.algorithms,

    // 导入导出状态（来自导入导出模块）
    importSettings: importModule.importSettings,

    // 计算属性（来自维度模块）
    hierarchicalDimensions: dimensionsModule.hierarchicalDimensions,
    groupedDimensions: dimensionsModule.groupedDimensions,
    isAllSelected: dimensionsModule.isAllSelected,

    // 生命周期（来自批量操作模块）
    initEvaluation: batchOpsModule.initEvaluation,
    cleanupEvaluation: batchOpsModule.cleanupEvaluation,

    // 模态框操作（来自模态框模块）
    openEditModal: modalsModule.openEditModal,
    openAddModal: modalsModule.openAddModal,
    openAddCategoryModal: modalsModule.openAddCategoryModal,

    // 搜索与过滤（来自维度模块）
    searchDimensions: dimensionsModule.searchDimensions,
    filterDimensions: dimensionsModule.filterDimensions,
    resetFilters: dimensionsModule.resetFilters,

    // 维度 CRUD（来自维度模块）
    deleteDimension: dimensionsModule.deleteDimension,
    toggleDimensionVisibility: dimensionsModule.toggleDimensionVisibility,

    // 维度排序（上移/下移，来自维度模块）
    moveDimension: dimensionsModule.moveDimension,
    canMoveUp: dimensionsModule.canMoveUp,
    canMoveDown: dimensionsModule.canMoveDown,

    // 批量操作（来自批量操作模块）
    batchEnable: batchOpsModule.batchEnable,
    batchDisable: batchOpsModule.batchDisable,
    batchDelete: batchOpsModule.batchDelete,
    toggleBatchMenu: batchOpsModule.toggleBatchMenu,
    toggleImportExportMenu: batchOpsModule.toggleImportExportMenu,

    // 维度选择（来自维度模块）
    toggleSelectAll: dimensionsModule.toggleSelectAll,
    toggleDimensionSelection: dimensionsModule.toggleDimensionSelection,
    groupAllSelected: dimensionsModule.groupAllSelected,
    toggleGroupSelectAll: dimensionsModule.toggleGroupSelectAll,

    // API 健康检查 / 权重（来自维度模块）
    testAPIHealth: dimensionsModule.testAPIHealth,
    updateWeight: dimensionsModule.updateWeight,

    // 导入导出（来自导入导出模块）
    importDimensions: importModule.importDimensions,
    exportDimensions: importModule.exportDimensions,

    // 工具方法（来自维度模块）
    getAlgorithmLabel: dimensionsModule.getAlgorithmLabel,

    // 状态重置（协调层）
    resetAllStates,

    // 工具方法（协调层）
    isLlmJudge,
  };
}
