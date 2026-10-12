import { ref, onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useTestCaseCard } from '../../composables/testCase/useTestCaseCard';
import { useTestCaseStore } from '../../store/testCaseStore';
import { useDeleteConfirm } from '../../composables/modal/useDeleteConfirm';
import { useNotification } from '../../composables/modal/useNotification';
import { useFavorites } from '../../composables/favorite/useFavorites';
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal';
import type { TestCase } from '../../domain';
import type { ModalSaveData } from '../../composables/modal/types';
// 引入视图模式枚举，消除魔法字符串
import { ViewMode, TestType } from '@/domain/enums';

/** ViewMode 枚举值类型（'group' | 'tag' 等） */
type ViewModeValue = typeof ViewMode[keyof typeof ViewMode];

/** 视图模式（TestCaseListContainer 仅支持 group/tag 两种） */
export type TestCaseViewMode = (typeof ViewMode.GROUP | typeof ViewMode.TAG);

export function useTestCaseManager() {
  const notification = useNotification();
  const {
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    openAddTestCaseModal,
    openEditTestCaseModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleModalSave,
    handleTestCaseAction
  } = useTestCaseCard();

  const store = useTestCaseStore();
  const modalControl = useModalControl();
  const { testCaseGroups, tagViewData, tags, paginationInfo, isLoading, tagViewPagination, tagViewLoading } = storeToRefs(store);
  const { fetchTestCases, fetchTagView, loadMoreTagView, deleteGroup: deleteGroupFromStore, deleteTestCase, resetGroupCache } = store;

  // ===== 收藏 / 回收站（INT-141）=====
  const favoritesModule = useFavorites('testcase');
  /** 仅看收藏 */
  const favoriteOnly = favoritesModule.favoriteOnly;
  /** 回收站模式（onlyDeleted 拉取 + 卡片操作切换为恢复/彻底删除） */
  const trashMode = ref(false);

  const currentFetchExtra = () => ({
    favorite: favoriteOnly.value && !trashMode.value,
    onlyDeleted: trashMode.value,
  });

  const handleFavoriteToggle = async (testCase: any) => {
    try {
      await favoritesModule.toggleFavorite(testCase.id);
      const fav = favoritesModule.isFavorite(testCase.id);
      // INT-215：就地回写行数据 isFavorite，星标态即时可见（无需整表重拉）
      store.patchTestCaseFavorite(testCase.id, fav);
      notification.success(fav ? '已收藏' : '已取消收藏');
    } catch (error) {
      notification.error('收藏操作失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleRestoreCase = async (testCase: any) => {
    try {
      const result = await favoritesModule.restore([testCase.id]);
      // INT-215：按后端 restored_count 判定真实结果，count=0 提示无可操作项而非假成功
      const restored = result?.restored_count ?? 0;
      if (restored > 0) {
        notification.success(`用例「${testCase.name}」已恢复`);
      } else {
        notification.info('无可恢复项（用例可能已被恢复）');
      }
      await refreshCurrentView();
    } catch (error) {
      notification.error('恢复用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handlePurgeCase = async (testCase: any) => {
    // INT-215：确认弹窗统一收敛到 BASIC_CONFIRM 模态（对齐全站危险操作范式）
    let confirmed = false;
    try {
      confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '彻底删除用例',
        content: `彻底删除用例「${testCase.name}」？该操作不可恢复（仅管理员/所有者可执行）。`,
        confirmText: '彻底删除',
        cancelText: '取消',
        danger: true,
      });
    } catch {
      return; // 用户取消
    }
    if (!confirmed) return;
    try {
      const result = await favoritesModule.purge([testCase.id]);
      // INT-215：按后端 purged_count 判定真实结果，count=0 提示无可操作项而非假成功
      const purged = result?.purged_count ?? 0;
      if (purged > 0) {
        notification.success(`用例「${testCase.name}」已彻底删除`);
      } else {
        notification.info('无可删除项（用例可能已被删除或不满足权限）');
      }
      await refreshCurrentView();
    } catch (error) {
      notification.error('彻底删除用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const restoreAllTrash = async () => {
    // INT-215：按当前过滤条件从后端取全量已删集合（原实现取分组视图缓存，
    // 标签视图下恢复错误集合或误报回收站为空）
    let ids: (string | number)[] = [];
    try {
      ids = await store.fetchCaseIdsByFilter({
        search: currentFilters.value.keyword,
        testType: currentFilters.value.testType,
        algorithmType: currentFilters.value.algorithmType,
        dimensionId: currentFilters.value.dimensionId,
        onlyDeleted: true,
      });
    } catch (error) {
      notification.error('获取回收站用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
      return;
    }
    if (ids.length === 0) {
      notification.info('回收站为空');
      return;
    }
    let confirmed = false;
    try {
      confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '全部恢复',
        content: `恢复回收站中的全部 ${ids.length} 个用例？`,
        confirmText: '全部恢复',
        cancelText: '取消',
      });
    } catch {
      return; // 用户取消
    }
    if (!confirmed) return;
    try {
      const result = await favoritesModule.restore(ids);
      const restored = result?.restored_count ?? 0;
      if (restored > 0) {
        notification.success(`已恢复 ${restored} 个用例`);
      } else {
        notification.info('无可恢复项（用例可能已被恢复）');
      }
      await refreshCurrentView();
    } catch (error) {
      notification.error('恢复失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const toggleTrashMode = async () => {
    trashMode.value = !trashMode.value;
    // INT-215：回收站模式下收藏筛选不可用——联动清空勾选态，避免静默失效
    if (trashMode.value && favoriteOnly.value) {
      favoriteOnly.value = false;
    }
    await refreshCurrentView();
  };

  // 视图模式：ViewMode.GROUP 分组视图 | ViewMode.TAG 标签视图
  const viewMode = ref<TestCaseViewMode>(ViewMode.GROUP);

  // 当前筛选条件（由 TestCaseListContainer 上报）
  const currentFilters = ref<{ keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }>({});

  const refreshCurrentView = async () => {
    if (viewMode.value === ViewMode.TAG) {
      await fetchTagView({
        keyword: currentFilters.value.keyword,
        testType: currentFilters.value.testType,
        algorithmType: currentFilters.value.algorithmType,
        dimensionId: currentFilters.value.dimensionId,
        // INT-215：收藏 / 回收站过滤贯通标签视图（原先漏传导致标签视图回收站断链）
        ...currentFetchExtra(),
      });
    } else {
      await fetchTestCases({
        keyword: currentFilters.value.keyword,
        testType: currentFilters.value.testType,
        algorithmType: currentFilters.value.algorithmType,
        dimensionId: currentFilters.value.dimensionId,
        ...currentFetchExtra(),
      });
    }
  };

  watch(viewMode, async (newMode) => {
    console.log('[TestCaseManager] 视图切换:', newMode);
    await refreshCurrentView();
  });

  // 由 TestCaseListContainer 上报筛选条件变化（标签视图）
  const handleTagFilterChange = (filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }) => {
    currentFilters.value = filters;
    if (viewMode.value === ViewMode.TAG) {
      fetchTagView({
        keyword: filters.keyword,
        testType: filters.testType,
        algorithmType: filters.algorithmType,
        dimensionId: filters.dimensionId,
        // INT-215：收藏 / 回收站过滤贯通标签视图
        ...currentFetchExtra(),
      });
    }
  };

  // 由 TestCaseListContainer 上报筛选条件变化（分组视图）
  const handleGroupFilterChange = (filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }) => {
    currentFilters.value = filters;
    if (viewMode.value === ViewMode.GROUP) {
      // 清空已加载分组用例,避免展开时显示旧筛选下的缓存数据。
      resetGroupCache();
      fetchTestCases({
        keyword: filters.keyword,
        testType: filters.testType,
        algorithmType: filters.algorithmType,
        dimensionId: filters.dimensionId,
        ...currentFetchExtra(),
      });
    }
  };

  const { confirmDeleteGroup, confirmDeleteTestCase } = useDeleteConfirm();

  const handleDeleteGroup = async (groupName: string) => {
    try {
      const confirmed = await confirmDeleteGroup(groupName);
      if (confirmed) {
        await deleteGroupFromStore(groupName);
        // 按当前视图刷新（标签视图下 tagViewData 需重新拉取）
        await refreshCurrentView();
      }
    } catch (error) {
      console.error('删除分组失败:', error);
      notification.error('删除分组失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleDeleteTestCase = async (testCase: TestCase) => {
    try {
      console.log('[TestCaseManager] 调用handleDeleteTestCase:', testCase.id, testCase.name);
      const confirmed = await confirmDeleteTestCase(testCase.name);
      if (confirmed) {
        await deleteTestCase(testCase.id);
        // 按当前视图刷新（标签视图下 tagViewData 需重新拉取）
        await refreshCurrentView();
      }
    } catch (error) {
      console.error('删除测试用例失败:', error);
      notification.error('删除测试用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleOpenEditModal = async (testCase: TestCase) => {
    const result = await openEditTestCaseModal(testCase);
    if (result?.needRefresh) {
      await refreshCurrentView();
    }
  };

  const handleOpenAddModal = async (group = '', options?: { algorithmType?: string; testType?: typeof TestType[keyof typeof TestType]; tags?: string[] }) => {
    const result = await openAddTestCaseModal(group, options);
    if (result?.needRefresh) {
      await refreshCurrentView();
    }
  };

  const handleSaveModal = async (data: ModalSaveData) => {
    const result = await handleModalSave(data);
    if (result?.needRefresh) {
      console.log('刷新测试用例数据...');
      await refreshCurrentView();
    }
  };

  onMounted(async () => {
    console.log('[TestCaseManager] 初始加载测试用例');
    await Promise.all([fetchTestCases(), favoritesModule.loadFavorites()]);
  });

  return {
    testCaseGroups,
    tagViewData,
    tags,
    paginationInfo,
    tagViewPagination,
    tagViewLoading,
    isLoading,
    viewMode,
    handleDeleteGroup,
    handleDeleteTestCase,
    openAddTestCaseModal,
    handleOpenAddModal,
    handleOpenEditModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleSaveModal,
    handleTestCaseAction,
    refreshCurrentView,
    handleTagFilterChange,
    handleGroupFilterChange,
    loadMoreTagView,
    // 收藏 / 回收站（INT-141）
    favoriteOnly,
    trashMode,
    toggleTrashMode,
    restoreAllTrash,
    handleFavoriteToggle,
    handleRestoreCase,
    handlePurgeCase,
  };
}
