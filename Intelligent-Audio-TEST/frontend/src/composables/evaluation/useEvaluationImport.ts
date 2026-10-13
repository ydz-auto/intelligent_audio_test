import { ref } from 'vue';
import { evaluationPort } from './evaluationPort';
import { useModalControl } from '../modal/useModal';
import { MODAL_TYPES } from '../modal/constants';
import { downloadBlob } from '../../utils/utils';
import type { UseEvaluationDimensionsReturn } from './useEvaluationDimensions';

/**
 * 评估维度导入导出组合式函数
 *
 * 职责：
 * - 导入维度（importDimensions / handleImport）
 * - 导出维度（exportDimensions）
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

  async function handleImport(file: File) {
    loading.value = true;
    try {
      const formData = new FormData();
      formData.append('file', file);
      // 单一参数通道：update_existing 走网关可识别的 camelCase 别名
      // （后端 FileImportInput 仅收 update_existing；skipErrors 后端无 schema 字段，已不再发送冗余参数）
      formData.append('updateExisting', importSettings.value.updateExisting ? 'true' : 'false');

      const result = await evaluationPort.import(formData);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '成功',
        content: `导入完成: 新增 ${result?.imported ?? 0} 条, 更新 ${result?.updated ?? 0} 条`,
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
  async function exportDimensions(format: 'json' | 'excel' = 'json') {
    loading.value = true;
    try {
      const blob = await evaluationPort.export(format);
      const extension = format === 'excel' ? 'xlsx' : 'json';
      downloadBlob(blob, `evaluation-dimensions-${new Date().toISOString().slice(0, 10)}.${extension}`);

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

  return {
    // 导入相关状态
    importSettings,
    // 导入
    importDimensions,
    handleImport,
    // 导出
    exportDimensions,
  };
}

export type UseEvaluationImportReturn = ReturnType<typeof useEvaluationImport>;
