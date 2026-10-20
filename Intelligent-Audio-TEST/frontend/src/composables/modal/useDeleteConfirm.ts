import { useModalControl } from './useModal';
import { MODAL_TYPES } from './constants';

export function useDeleteConfirm() {
  const { open, closeAll } = useModalControl();

  const confirmDelete = async (title: string, content: string): Promise<boolean> => {
    try {
      closeAll();
      await new Promise(resolve => setTimeout(resolve, 100));
      const confirmed = await open(MODAL_TYPES.BASIC_CONFIRM, {
        title,
        content,
        danger: true,
        confirmText: '删除',
        cancelText: '取消'
      });
      return confirmed;
    } catch (error) {
      console.error('[useDeleteConfirm] 确认删除失败:', error);
      return false;
    }
  };

  const confirmDeleteGroup = async (groupName: string): Promise<boolean> => {
    return confirmDelete(
      '确认删除',
      `确定要删除分组 "${groupName}" 及其下所有测试用例吗？此操作不可逆！`
    );
  };

  const confirmDeleteTestCase = async (testCaseName: string): Promise<boolean> => {
    return confirmDelete(
      '确认删除',
      `确定要删除测试用例 "${testCaseName}" 吗？`
    );
  };

  return {
    confirmDelete,
    confirmDeleteGroup,
    confirmDeleteTestCase
  };
}
