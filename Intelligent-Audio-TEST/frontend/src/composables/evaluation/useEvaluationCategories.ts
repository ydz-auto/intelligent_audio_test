import { ref } from 'vue';
import { evaluationApi } from '../../utils/api';
import { useModalControl } from '../modal/useModal';
import { EvaluationCategory, MODAL_TYPES } from '../../shared/types';
import type { UseEvaluationDimensionsReturn } from './useEvaluationDimensions';

/**
 * 评估分类管理组合式函数
 *
 * 职责：
 * - 分类 CRUD（saveCategory / deleteGroup）
 * - 分类展开/折叠（toggleCategory）
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

  // ========== 分类展开/折叠 ==========
  function toggleCategory(categoryHeader: HTMLElement, event: MouseEvent) {
    event.stopPropagation();
    const categoryContent = categoryHeader.querySelector('.category-content');
    const toggleIcon = categoryHeader.querySelector('.category-toggle');
    if (categoryContent) {
      categoryContent.classList.toggle('collapsed');
      if (toggleIcon) toggleIcon.classList.toggle('rotate');
    }
  }

  // ========== 分类 CRUD ==========
  async function deleteGroup(id: number) {
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '删除分类',
      content: `确定要删除该分类吗？此操作将同时删除该分类下的所有维度。`,
      onConfirm: async () => {
        loading.value = true;
        try {
          await evaluationApi.deleteCategory(id);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '成功',
            content: '分类已删除',
            onConfirm: () => {
            }
          });
          await fetchData();
        } catch (err: any) {
          console.error('Failed to delete category:', err);
          modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '错误',
            content: err.message || '删除分类失败',
            onConfirm: () => {
            }
          });
        } finally {
          loading.value = false;
        }
      }
    });
  }

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
        await evaluationApi.createCategory(data);
        modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '成功',
          content: '分类添加成功',
          onConfirm: () => {
          }
        });
        newCategory.value = { name: '', description: '', icon: 'fas fa-tachometer-alt' };
      } else {
        if (!data.id) throw new Error('分类 ID 缺失');
        await evaluationApi.updateCategory(data.id, data);
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
        content: err.message || '保存分类失败',
        onConfirm: () => {
        }
      });
    } finally {
      loading.value = false;
    }
  }

  return {
    newCategory,
    toggleCategory,
    deleteGroup,
    saveCategory,
  };
}

export type UseEvaluationCategoriesReturn = ReturnType<typeof useEvaluationCategories>;
