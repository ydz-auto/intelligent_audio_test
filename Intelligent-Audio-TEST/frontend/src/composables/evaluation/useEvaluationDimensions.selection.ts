/**
 * useEvaluationDimensions —— 维度选择
 *
 * 负责列表的全选/单选切换与分组维度批量勾选逻辑。
 */
import type { EvalDimensionState } from './useEvaluationDimensions.state';

/** 创建维度选择模块 */
export function createEvalDimensionSelection(state: EvalDimensionState) {
  const {
    selectedDimensions,
    dimensions,
    filteredDimensions,
    isAllSelected,
  } = state;

  // ========== 维度选择 ==========
  function toggleSelectAll() {
    if (isAllSelected.value) {
      selectedDimensions.value = [];
    } else {
      selectedDimensions.value = filteredDimensions.value.map(dim => dim.id);
    }
  }

  function toggleDimensionSelection(id: number | string) {
    const index = selectedDimensions.value.indexOf(id);
    if (index > -1) {
      selectedDimensions.value.splice(index, 1);
    } else {
      selectedDimensions.value.push(id);
    }
  }

  function toggleGroupSelection(groupCheckbox: HTMLInputElement, category: string) {
    const isChecked = groupCheckbox.checked;
    const dimensionsInCategory = dimensions.value.filter(dim => dim.type === category);

    if (isChecked) {
      dimensionsInCategory.forEach(dim => {
        if (!selectedDimensions.value.includes(dim.id)) {
          selectedDimensions.value.push(dim.id);
        }
      });
    } else {
      selectedDimensions.value = selectedDimensions.value.filter(id => {
        return !dimensionsInCategory.some(dim => dim.id === id);
      });
    }
  }

  function selectAllInGroup(category: string) {
    const dimensionsInCategory = dimensions.value.filter(dim => dim.type === category);
    dimensionsInCategory.forEach(dim => {
      if (!selectedDimensions.value.includes(dim.id)) {
        selectedDimensions.value.push(dim.id);
      }
    });
  }

  function toggleSelectAllInCategory(category: string) {
    const dimensionsInCategory = dimensions.value.filter(dim => dim.type === category);
    const allSelected = dimensionsInCategory.every(dim => selectedDimensions.value.includes(dim.id));

    if (allSelected) {
      selectedDimensions.value = selectedDimensions.value.filter(id => {
        return !dimensionsInCategory.some(dim => dim.id === id);
      });
    } else {
      dimensionsInCategory.forEach(dim => {
        if (!selectedDimensions.value.includes(dim.id)) {
          selectedDimensions.value.push(dim.id);
        }
      });
    }
  }

  // ========== 分组视图组内全选 ==========
  /** 分组视图：组内维度是否全部选中 */
  function groupAllSelected(group: { items: Array<{ id: number | string }> }): boolean {
    const ids = group.items.map(d => d.id);
    return ids.length > 0 && ids.every(id => selectedDimensions.value.includes(id));
  }

  /** 分组视图：切换组内全选状态 */
  function toggleGroupSelectAll(group: { items: Array<{ id: number | string }> }) {
    const ids = group.items.map(d => d.id);
    const allSelected = ids.every(id => selectedDimensions.value.includes(id));
    if (allSelected) {
      const idSet = new Set(ids);
      selectedDimensions.value = selectedDimensions.value.filter(id => !idSet.has(id));
    } else {
      ids.forEach(id => {
        if (!selectedDimensions.value.includes(id)) selectedDimensions.value.push(id);
      });
    }
  }

  return {
    toggleSelectAll,
    toggleDimensionSelection,
    toggleGroupSelection,
    selectAllInGroup,
    toggleSelectAllInCategory,
    groupAllSelected,
    toggleGroupSelectAll,
  };
}

/** 维度选择模块类型（由工厂推断） */
export type EvalDimensionSelectionModule = ReturnType<typeof createEvalDimensionSelection>;
