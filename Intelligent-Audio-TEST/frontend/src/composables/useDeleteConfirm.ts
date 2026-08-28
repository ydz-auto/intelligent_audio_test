import { useModalControl } from './useModal';
import { MODAL_TYPES } from '../shared/types';

export function useDeleteConfirm() {
  const { open, closeAll } = useModalControl();

  const confirmDelete = async (title: string, content: string): Promise<boolean> => {
    try {
      console.log('[useDeleteConfirm] 开始确认删除流程, title:', title, 'content:', content);
      closeAll();
      await new Promise(resolve => setTimeout(resolve, 100));
      console.log('[useDeleteConfirm] 准备打开确认模态框');
      const confirmed = await open(MODAL_TYPES.BASIC_CONFIRM, {
        title,
        content,
        danger: true,
        confirmText: '删除',
        cancelText: '取消'
      });
      console.log('[useDeleteConfirm] 用户选择结果:', confirmed);
      return confirmed;
    } catch (error) {
      console.error('[useDeleteConfirm] 确认删除失败:', error);
      return false;
    }
  };

  const confirmDeleteGroup = async (groupName: string): Promise<boolean> => {
    console.log('[useDeleteConfirm] confirmDeleteGroup 被调用, groupName:', groupName);
    return confirmDelete(
      '确认删除',
      `确定要删除分组 "${groupName}" 及其下所有测试用例吗？此操作不可逆！`
    );
  };

  const confirmDeleteTag = async (tagName: string): Promise<boolean> => {
    console.log('[useDeleteConfirm] confirmDeleteTag 被调用, tagName:', tagName);
    return confirmDelete(
      '确认删除',
      `确定要删除标签 "${tagName}" 及其下所有测试用例吗？此操作不可逆！`
    );
  };

  const confirmDeleteTestCase = async (testCaseName: string): Promise<boolean> => {
    console.log('[useDeleteConfirm] confirmDeleteTestCase 被调用, testCaseName:', testCaseName);
    return confirmDelete(
      '确认删除',
      `确定要删除测试用例 "${testCaseName}" 吗？`
    );
  };

  return {
    confirmDelete,
    confirmDeleteGroup,
    confirmDeleteTag,
    confirmDeleteTestCase
  };
}
