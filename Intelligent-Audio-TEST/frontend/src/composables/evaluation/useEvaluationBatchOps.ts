import { ref } from 'vue';
import { evaluationApi } from '../../utils/api';
import { useModalControl } from '../modal/useModal';
import { MODAL_TYPES } from '../../shared/types';
import type { UseEvaluationDimensionsReturn } from './useEvaluationDimensions';

/**
 * 评估批量操作组合式函数
 *
 * 职责：
 * - 批量启用/禁用/删除维度（batchEnable / batchDisable / batchDelete）
 * - 批量菜单与导入导出菜单的 UI 状态与点击外部关闭逻辑
 * - 初始化与清理（initEvaluation / cleanupEvaluation）
 *
 * 依赖维度模块：loading、selectedDimensions、fetchData
 */

export function useEvaluationBatchOps(dimensionsModule: UseEvaluationDimensionsReturn) {
  const modalManager = useModalControl();

  const { loading, selectedDimensions, fetchData } = dimensionsModule;

  // ========== UI 状态 ==========
  const batchMenuRef = ref<HTMLElement | null>(null);
  const importExportMenuRef = ref<HTMLElement | null>(null);

  // ========== 菜单切换 ==========
  function toggleBatchMenu() {
    const batchMenu = document.getElementById('batchMenu');
    if (batchMenu) batchMenu.classList.toggle('active');
  }

  function toggleImportExportMenu() {
    const importExportMenu = document.getElementById('importExportMenu');
    if (importExportMenu) importExportMenu.classList.toggle('active');
  }

  // ========== 点击外部关闭 ==========
  function handleClickOutside(event: MouseEvent) {
    if (batchMenuRef.value && !batchMenuRef.value.contains(event.target as Node)) {
      const batchMenu = document.getElementById('batchMenu');
      if (batchMenu) {
        batchMenu.classList.remove('active');
      }
    }

    if (importExportMenuRef.value && !importExportMenuRef.value.contains(event.target as Node)) {
      const importExportMenu = document.getElementById('importExportMenu');
      if (importExportMenu) {
        importExportMenu.classList.remove('active');
      }
    }
  }

  function initEvaluation() {
    fetchData();
    window.addEventListener('click', handleClickOutside);
  }

  function cleanupEvaluation() {
    window.removeEventListener('click', handleClickOutside);
  }

  // ========== 批量操作 ==========
  async function batchEnable() {
    if (selectedDimensions.value.length === 0) {
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '提示',
        content: '请先选择要启用的维度',
        onConfirm: () => {
        }
      });
      return;
    }
    loading.value = true;
    try {
      await evaluationApi.batchAction('enable', selectedDimensions.value);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: '批量启用成功',
        onConfirm: () => {
        }
      });
      await fetchData();
    } catch (err: any) {
      console.error('Failed to batch enable dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: err.message || '批量启用失败',
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function batchDisable() {
    if (selectedDimensions.value.length === 0) {
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '提示',
        content: '请先选择要禁用的维度',
        onConfirm: () => {
        }
      });
      return;
    }
    loading.value = true;
    try {
      await evaluationApi.batchAction('disable', selectedDimensions.value);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: '批量禁用成功',
        onConfirm: () => {
        }
      });
      await fetchData();
    } catch (err: any) {
      console.error('Failed to batch disable dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: err.message || '批量禁用失败',
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function batchDelete() {
    if (selectedDimensions.value.length === 0) {
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '提示',
        content: '请先选择要删除的维度',
        onConfirm: () => {
        }
      });
      return;
    }

    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '批量删除维度',
      content: `确定要删除选中的 ${selectedDimensions.value.length} 个维度吗？`,
      onConfirm: async () => {
        loading.value = true;
        try {
          await evaluationApi.batchAction('delete', selectedDimensions.value);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '成功',
            content: '批量删除成功',
            onConfirm: () => {
            }
          });
          selectedDimensions.value = [];
          await fetchData();
        } catch (err: any) {
          console.error('Failed to batch delete dimensions:', err);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '错误',
            content: err.message || '批量删除失败',
            onConfirm: () => {
            }
          });
        } finally {
          loading.value = false;
        }
      }
    });
  }

  return {
    // UI 状态
    batchMenuRef,
    importExportMenuRef,
    // 菜单切换
    toggleBatchMenu,
    toggleImportExportMenu,
    // 生命周期
    initEvaluation,
    cleanupEvaluation,
    // 批量操作
    batchEnable,
    batchDisable,
    batchDelete,
  };
}

export type UseEvaluationBatchOpsReturn = ReturnType<typeof useEvaluationBatchOps>;
