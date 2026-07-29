import { ref } from 'vue';
import { evaluationApi } from '../utils/api';
import { useModalControl } from './useModal';
import { MODAL_TYPES } from '../shared/types';
import type { UseEvaluationDimensionsReturn } from './useEvaluationDimensions';

/**
 * 评估维度导入导出组合式函数
 *
 * 职责：
 * - 导入维度（importDimensions / handleImport / previewImportData）
 * - 导出维度（exportData / exportDimensions）
 *
 * 依赖维度模块：loading、fetchData
 */

export function useEvaluationImport(dimensionsModule: UseEvaluationDimensionsReturn) {
  const modalManager = useModalControl();

  const { loading, fetchData } = dimensionsModule;

  // ========== 导入相关状态 ==========
  const importSettings = ref({
    updateExisting: true,
    skipErrors: false
  });

  const showImportPreview = ref(false);
  const importPreview = ref({
    fileName: '',
    format: '',
    totalCount: 0
  });

  // ========== 导入 ==========
  function importDimensions() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx,.xls,.json';
    input.style.display = 'none';

    input.addEventListener('change', async (event: any) => {
      const file = event.target.files[0];
      if (file) {
        await handleImport(file);
      }
      input.remove();
    });

    document.body.appendChild(input);
    input.click();
  }

  function previewImportData(event: any) {
    const file = event.target.files[0];
    if (file) {
      showImportPreview.value = true;
      importPreview.value = { fileName: file.name, format: file.name.split('.').pop().toUpperCase(), totalCount: 0 };
    }
  }

  async function handleImport(file: File) {
    loading.value = true;
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('updateExisting', importSettings.value.updateExisting ? 'true' : 'false');
      formData.append('skipErrors', importSettings.value.skipErrors ? 'true' : 'false');

      const result = await evaluationApi.import(formData);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: `导入成功: ${result.message || '已完成'}`,
        onConfirm: () => {
        }
      });
      await fetchData();
    } catch (err: any) {
      console.error('Failed to import dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `导入维度失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  // ========== 导出 ==========
  async function exportData(format: 'json' | 'excel' = 'json') {
    loading.value = true;
    try {
      const blob = await evaluationApi.export(format);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const extension = format === 'excel' ? 'xlsx' : 'json';
      link.download = `evaluation-dimensions-${new Date().toISOString().slice(0, 10)}.${extension}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: '维度导出成功',
        onConfirm: () => {
        }
      });
    } catch (err: any) {
      console.error('Failed to export dimensions:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: `导出维度失败: ${err.message || '未知错误'}`,
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  async function exportDimensions(format: 'json' | 'excel' = 'json') {
    return exportData(format);
  }

  return {
    // 导入相关状态
    importSettings,
    showImportPreview,
    importPreview,
    // 导入
    importDimensions,
    previewImportData,
    handleImport,
    // 导出
    exportData,
    exportDimensions,
  };
}

export type UseEvaluationImportReturn = ReturnType<typeof useEvaluationImport>;
