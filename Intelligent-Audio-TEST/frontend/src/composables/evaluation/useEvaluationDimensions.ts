/**
 * useEvaluationDimensions —— 组合根（Composition Root）
 *
 * 原单一超大文件已按职责拆分为同目录 useEvaluationDimensions.*.ts 子模块：
 * - constants  常量定义（新建分类标识、维度类型、各类默认值、保存操作类型）
 * - state      共享响应式状态（refs/模板/表单初值/派生计算属性/算法标签工具）
 * - loaders    数据加载与分页过滤（fetchData + 筛选/分页导航）
 * - form       表单字段动态定义（evaluationFields）与必填字段校验
 * - selection  维度选择（全选/单选/分组批量勾选）
 * - normalize  保存前字段规范化处理链（rule/requiredInputs/categoryId/层级继承等）
 * - save       维度保存/删除编排与 API 健康检查、权重更新
 * 本文件仅负责按依赖顺序组装各模块并聚合原有全部导出，
 * 模块路径、导出面与返回对象形状保持不变，消费方零改动。
 */
import { useModalControl } from '../modal/useModal';
import { createEvalDimensionState } from './useEvaluationDimensions.state';
import { createEvalDimensionForm } from './useEvaluationDimensions.form';
import { createEvalDimensionLoaders } from './useEvaluationDimensions.loaders';
import { createEvalDimensionSelection } from './useEvaluationDimensions.selection';
import { createEvalDimensionNormalizers } from './useEvaluationDimensions.normalize';
import { createEvalDimensionSave } from './useEvaluationDimensions.save';

// 重新导出编辑模态框使用的扩展 API 设置类型，保持对外接口兼容
export type { ExtendedAPISettings } from './useEvaluationDimensions.state';

/**
 * 评估维度管理组合式函数
 *
 * 职责：
 * - 维度列表数据获取（含分类、算法）
 * - 维度 CRUD（saveDimension / deleteDimension）
 * - 维度选择（toggleSelectAll / toggleDimensionSelection / 分组选择）
 * - 分页与过滤（goToPage / searchDimensions / resetFilters 等）
 * - 维度表单字段定义（evaluationFields）
 * - API 健康检查、权重更新、算法标签
 *
 * 该模块为基础模块，其他子模块通过参数注入其返回值。
 */

export function useEvaluationDimensions() {
  const modalManager = useModalControl();

  // 1. 共享状态（refs / 模板 / 表单初值 / 派生计算属性 / 工具方法）
  const state = createEvalDimensionState();
  const {
    loading,
    error,
    dimensions,
    categories,
    algorithms,
    apiHealthResult,
    editingCategory,
    editingDimension,
    searchKeyword,
    filterStatus,
    filterCategory,
    selectedDimensions,
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    dimensionTemplate,
    newDimension,
    apiSettings,
    filteredDimensions,
    isAllSelected,
    hierarchicalDimensions,
    getAlgorithmLabel,
  } = state;

  // 2. 表单字段动态定义与必填字段校验
  const { evaluationFields, validateRequiredFields } = createEvalDimensionForm(state);

  // 3. 数据加载与分页过滤
  const {
    fetchData,
    goToPage,
    prevPage,
    nextPage,
    onPageSizeChange,
    searchDimensions,
    filterDimensions,
    resetFilters,
  } = createEvalDimensionLoaders(state);

  // 4. 维度选择（全选 / 单选 / 分组批量勾选）
  const {
    toggleSelectAll,
    toggleDimensionSelection,
    toggleGroupSelection,
    selectAllInGroup,
    toggleSelectAllInCategory,
  } = createEvalDimensionSelection(state);

  // 5. 保存前字段规范化处理链
  const normalizers = createEvalDimensionNormalizers(state);

  // 6. 维度保存 / 删除编排与 API 健康检查、权重更新
  const {
    saveDimension,
    deleteDimension,
    testAPIHealth,
    updateWeight,
  } = createEvalDimensionSave(state, {
    modalManager,
    fetchData,
    validateRequiredFields,
    normalizers,
  });

  return {
    // 基础状态
    loading,
    error,
    dimensions,
    categories,
    algorithms,
    apiHealthResult,
    editingCategory,
    editingDimension,
    // 过滤与分页状态
    searchKeyword,
    filterStatus,
    filterCategory,
    selectedDimensions,
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    // 模板与表单数据
    dimensionTemplate,
    newDimension,
    apiSettings,
    // 计算属性
    filteredDimensions,
    hierarchicalDimensions,
    isAllSelected,
    evaluationFields,
    // 数据获取
    fetchData,
    // 分页与过滤
    goToPage,
    prevPage,
    nextPage,
    onPageSizeChange,
    searchDimensions,
    filterDimensions,
    resetFilters,
    // 维度选择
    toggleSelectAll,
    toggleDimensionSelection,
    toggleGroupSelection,
    selectAllInGroup,
    toggleSelectAllInCategory,
    // 维度 CRUD
    saveDimension,
    deleteDimension,
    // API 健康检查 / 权重
    testAPIHealth,
    updateWeight,
    // 工具方法
    getAlgorithmLabel,
  };
}

export type UseEvaluationDimensionsReturn = ReturnType<typeof useEvaluationDimensions>;
