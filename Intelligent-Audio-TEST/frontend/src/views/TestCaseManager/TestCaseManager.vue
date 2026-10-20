<template>
  <div class="test-case-manager">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-tasks"></i>
          测试用例管理
        </h2>
        <p class="page-description">统一管理端到端测试用例和API测试用例</p>
      </div>
    </div>
    
    <!-- INT-141：收藏 / 回收站工具栏（INT-215：收敛至 common 组件，三视图统一口径） -->
    <FavoriteTrashBar
      :favorite-only="favoriteOnly"
      :trash-mode="trashMode"
      :favorite-disabled="trashMode"
      show-restore-all
      restore-all-title="恢复回收站中的全部用例"
      @update:favorite-only="onFavoriteFilterChange"
      @update:trash-mode="toggleTrashMode"
      @restore-all="restoreAllTrash"
    />

    <TestCaseListContainer
      :test-case-groups="testCaseGroups"
      :tag-view-data="tagViewData"
      :tags="tags"
      :tag-view-pagination="tagViewPagination"
      :tag-view-loading="tagViewLoading"
      :pagination-info="paginationInfo"
      :is-loading="isLoading"
      :trash-mode="trashMode"
      :visibility-filter="visibilityFilter"
      v-model:view-mode="viewMode"
      @delete-group="handleDeleteGroup"
      @delete-test-case="handleDeleteTestCase"
      @open-add-modal="handleOpenAddModal"
      @open-edit-modal="handleOpenEditModal"
      @open-create-group-modal="openCreateGroupModal"
      @open-edit-group-modal="openEditGroupModal"
      @open-import-modal="openImportTestCaseModal"
      @open-export-modal="openExportTestCaseModal"
      @tag-filter-change="handleTagFilterChange"
      @group-filter-change="handleGroupFilterChange"
      @visibility-filter-change="handleVisibilityFilterChange"
      @load-more-tags="loadMoreTagView"
      @favorite-toggle="handleFavoriteToggle"
      @restore-case="handleRestoreCase"
      @purge-case="handlePurgeCase"
    />
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'
import "../../assets/styles/test-case-manager/base.css"
import "../../assets/styles/test-case-manager/toolbar.css"
import "../../assets/styles/test-case-manager/category.css"
import "../../assets/styles/test-case-manager/test-case-manager.css"
import TestCaseListContainer from '../../components/common/test-case/TestCaseListContainer.vue';
import FavoriteTrashBar from '../../components/common/FavoriteTrashBar.vue';
import { useTestCaseManager } from './TestCaseManager';

const {
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
  handleTagFilterChange,
  handleGroupFilterChange,
  loadMoreTagView,
  // 收藏 / 回收站（INT-141）
  favoriteOnly,
  trashMode,
  toggleTrashMode,
  refreshCurrentView,
  restoreAllTrash,
  handleFavoriteToggle,
  handleRestoreCase,
  handlePurgeCase,
  // INT-423/467：可见性筛选
  visibilityFilter,
  handleVisibilityFilterChange
} = useTestCaseManager();

/** INT-215：收藏筛选切换后按当前视图刷新（与回收站模式互斥联动由 toggleTrashMode 收敛） */
const onFavoriteFilterChange = (value: boolean) => {
  favoriteOnly.value = value;
  refreshCurrentView();
};
</script>

<style scoped>
.test-case-manager{
    padding: 24px;
}
/* 页面标题品牌色（原内联 style 迁入，INT-739 CSS 冻结） */
.test-case-manager .page-title {
    color: var(--primary, var(--color-indigo-500));
}
</style>
