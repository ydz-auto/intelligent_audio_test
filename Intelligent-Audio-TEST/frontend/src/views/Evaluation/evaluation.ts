import { onMounted, onBeforeUnmount } from 'vue';
import { useEvaluationDimensions } from '../../composables/evaluation/useEvaluationDimensions';
import { useEvaluationCategories } from '../../composables/evaluation/useEvaluationCategories';
import { useEvaluationBatchOps } from '../../composables/evaluation/useEvaluationBatchOps';
import { useEvaluationImport } from '../../composables/evaluation/useEvaluationImport';
import { useEvaluationModals } from '../../composables/evaluation/useEvaluationModals';

// 重新导出类型以保持对外接口兼容
export type { ExtendedAPISettings } from '../../composables/evaluation/useEvaluationDimensions';

/**
 * useEvaluation - 轻量级协调层
 *
 * 组合以下子模块，暴露统一接口给 Evaluation.vue 使用：
 * - useEvaluationDimensions: 维度管理（CRUD、批量选择、分页/过滤、API健康检查、权重）
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

  // 5. 模态框模块（依赖维度模块的 dimensions/evaluationFields/dimensionTemplate/saveDimension/apiSettings/loading）
  const modalsModule = useEvaluationModals(dimensionsModule);

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
    dimensionsModule.currentPage.value = 1;
    dimensionsModule.pageSize.value = 10;
    dimensionsModule.selectedDimensions.value = [];
    dimensionsModule.newDimension.value = { ...dimensionsModule.dimensionTemplate } as any;
    importModule.importSettings.value = { updateExisting: true, skipErrors: false };
    importModule.showImportPreview.value = false;
    categoriesModule.newCategory.value = { name: '', description: '', icon: 'fas fa-tachometer-alt' };
  }

  // ========== 暴露统一接口（与原 useEvaluation 完全兼容） ==========

  return {
    // 基础状态（来自维度模块）
    loading: dimensionsModule.loading,
    error: dimensionsModule.error,
    apiHealthResult: dimensionsModule.apiHealthResult,
    editingCategory: dimensionsModule.editingCategory,
    editingDimension: dimensionsModule.editingDimension,

    // UI 引用（来自批量操作模块）
    batchMenuRef: batchOpsModule.batchMenuRef,
    importExportMenuRef: batchOpsModule.importExportMenuRef,

    // 过滤与分页状态（来自维度模块）
    searchKeyword: dimensionsModule.searchKeyword,
    filterStatus: dimensionsModule.filterStatus,
    filterCategory: dimensionsModule.filterCategory,
    selectedDimensions: dimensionsModule.selectedDimensions,
    currentPage: dimensionsModule.currentPage,
    pageSize: dimensionsModule.pageSize,
    totalItems: dimensionsModule.totalItems,
    totalPages: dimensionsModule.totalPages,

    // 数据列表（来自维度模块）
    dimensions: dimensionsModule.dimensions,
    categories: dimensionsModule.categories,
    algorithms: dimensionsModule.algorithms,
    newDimension: dimensionsModule.newDimension,
    apiSettings: dimensionsModule.apiSettings,

    // 导入导出状态（来自导入导出模块）
    importSettings: importModule.importSettings,
    showImportPreview: importModule.showImportPreview,
    importPreview: importModule.importPreview,

    // 分类状态（来自分类模块）
    newCategory: categoriesModule.newCategory,

    // 计算属性（来自维度模块）
    filteredDimensions: dimensionsModule.filteredDimensions,
    isAllSelected: dimensionsModule.isAllSelected,

    // 数据获取（来自维度模块）
    fetchData: dimensionsModule.fetchData,

    // 生命周期（来自批量操作模块）
    initEvaluation: batchOpsModule.initEvaluation,
    cleanupEvaluation: batchOpsModule.cleanupEvaluation,

    // 模态框操作（来自模态框模块）
    openEditModal: modalsModule.openEditModal,
    openAddModal: modalsModule.openAddModal,
    openAPISettingsModal: modalsModule.openAPISettingsModal,
    openRuleEditorModal: modalsModule.openRuleEditorModal,
    saveAPISettings: modalsModule.saveAPISettings,
    closeModal: modalsModule.closeModal,

    // 分页与过滤（来自维度模块）
    goToPage: dimensionsModule.goToPage,
    prevPage: dimensionsModule.prevPage,
    nextPage: dimensionsModule.nextPage,
    onPageSizeChange: dimensionsModule.onPageSizeChange,
    searchDimensions: dimensionsModule.searchDimensions,
    filterDimensions: dimensionsModule.filterDimensions,
    resetFilters: dimensionsModule.resetFilters,

    // 维度 CRUD（来自维度模块）
    saveDimension: dimensionsModule.saveDimension,
    deleteDimension: dimensionsModule.deleteDimension,

    // 批量操作（来自批量操作模块）
    batchEnable: batchOpsModule.batchEnable,
    batchDisable: batchOpsModule.batchDisable,
    batchDelete: batchOpsModule.batchDelete,
    toggleBatchMenu: batchOpsModule.toggleBatchMenu,
    toggleImportExportMenu: batchOpsModule.toggleImportExportMenu,

    // 维度选择（来自维度模块）
    toggleSelectAll: dimensionsModule.toggleSelectAll,
    toggleDimensionSelection: dimensionsModule.toggleDimensionSelection,
    toggleGroupSelection: dimensionsModule.toggleGroupSelection,
    selectAllInGroup: dimensionsModule.selectAllInGroup,
    toggleSelectAllInCategory: dimensionsModule.toggleSelectAllInCategory,

    // API 健康检查 / 权重（来自维度模块）
    testAPIHealth: dimensionsModule.testAPIHealth,
    updateWeight: dimensionsModule.updateWeight,

    // 导入导出（来自导入导出模块）
    importDimensions: importModule.importDimensions,
    exportData: importModule.exportData,
    exportDimensions: importModule.exportDimensions,
    previewImportData: importModule.previewImportData,
    handleImport: importModule.handleImport,

    // 分类管理（来自分类模块）
    toggleCategory: categoriesModule.toggleCategory,
    deleteGroup: categoriesModule.deleteGroup,
    saveCategory: categoriesModule.saveCategory,

    // 工具方法（来自维度模块）
    getAlgorithmLabel: dimensionsModule.getAlgorithmLabel,

    // 状态重置（协调层）
    resetAllStates,

    // 工具方法（协调层）
    isLlmJudge,
  };
}
