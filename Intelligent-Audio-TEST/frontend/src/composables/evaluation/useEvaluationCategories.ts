import { ref } from 'vue';
import { evaluationPort } from './evaluationPort';
import { useModalControl } from '../modal/useModal';
import { EvaluationCategory } from '../../domain';
import { MODAL_TYPES } from '../modal/constants';
import { toUserErrorMessage } from '../../utils/errorMessage';
import type { UseEvaluationDimensionsReturn } from './useEvaluationDimensions';

/**
 * 评估分类管理组合式函数
 *
 * 职责：
 * - 分类 CRUD（saveCategory；分类删除/展开折叠已随 V9.7.31 分组视图重构移除，
 *   分组展示由 useEvaluationDimensions.groupedDimensions + isGroupExpanded 承载）
 *
 * 依赖维度模块：loading、categories、fetchData
 */

export function useEvaluationCategories(dimensionsModule: UseEvaluationDimensionsReturn) {
  const modalManager = useModalControl();

  // 复用维度模块的 loading 与 categories，确保状态同步
  const { loading, categories, fetchData } = dimensionsModule;

  const newCategory = ref<Partial<EvaluationCategory>>({
    name: '',
    description: '',
    icon: 'fas fa-tachometer-alt'
  });

  // ========== 分类 CRUD ==========
  async function saveCategory(data: any, type: 'add' | 'edit' = 'add') {
    loading.value = true;
    try {
      const missingFields: string[] = [];

      if (!data.name) {
        missingFields.push('分类名称');
      }

      if (missingFields.length > 0) {
        throw new Error(`以下必填字段缺失：${missingFields.join('、')}`);
      }

      if (type === 'add') {
        await evaluationPort.createCategory(data);
        modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '成功',
          content: '分类添加成功',
          onConfirm: () => {
          }
        });
        newCategory.value = { name: '', description: '', icon: 'fas fa-tachometer-alt' };
      } else {
        if (!data.id) throw new Error('分类 ID 缺失');
        await evaluationPort.updateCategory(data.id, data);
        modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '成功',
          content: '分类更新成功',
          onConfirm: () => {
          }
        });
      }
      await fetchData();
    } catch (err: any) {
      console.error('Failed to save category:', err);
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '错误',
        content: toUserErrorMessage(err, '保存分类失败'),
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  return {
    newCategory,
    saveCategory,
  };
}

export type UseEvaluationCategoriesReturn = ReturnType<typeof useEvaluationCategories>;
