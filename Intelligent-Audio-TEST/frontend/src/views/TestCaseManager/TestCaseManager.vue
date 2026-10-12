<template>
  <div class="test-case-manager">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-tasks"></i>
          测试用例管理
        </h2>
        <p class="page-description">统一管理端到端测试用例和API测试用例</p>
      </div>
    </div>
    
    <!-- INT-141：收藏 / 回收站工具栏 -->
    <div class="favorite-trash-bar">
      <label class="bar-toggle" :class="{ active: favoriteOnly }" title="仅显示我收藏的用例">
        <input type="checkbox" v-model="favoriteOnly" @change="refreshCurrentView">
        <i class="fas fa-star"></i> 仅看收藏
      </label>
      <button class="bar-toggle" :class="{ active: trashMode }" @click="toggleTrashMode" title="回收站：已删除用例，可恢复或彻底删除">
        <i class="fas fa-trash-restore"></i> 回收站
      </button>
      <button v-if="trashMode" class="bar-toggle" @click="restoreAllTrash" title="恢复回收站中的全部用例">
        <i class="fas fa-undo"></i> 全部恢复
      </button>
    </div>

    <TestCaseListContainer
      :test-case-groups="testCaseGroups"
      :tag-view-data="tagViewData"
      :tags="tags"
      :tag-view-pagination="tagViewPagination"
      :tag-view-loading="tagViewLoading"
      :pagination-info="paginationInfo"
      :is-loading="isLoading"
      :trash-mode="trashMode"
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
      @load-more-tags="loadMoreTagView"
      @favorite-toggle="handleFavoriteToggle"
      @restore-case="handleRestoreCase"
      @purge-case="handlePurgeCase"
    />
  </div>
</template>

<script setup lang="ts">
import TestCaseListContainer from '../../components/common/test-case/TestCaseListContainer.vue';
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
  handlePurgeCase
} = useTestCaseManager();
</script>

<style scoped>
.test-case-manager{
    padding: 24px;
}

/* INT-141：收藏 / 回收站工具栏 */
.favorite-trash-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.bar-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--background-primary);
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  color: inherit;
}
.bar-toggle.active {
  border-color: var(--primary);
  color: var(--primary);
}
.bar-toggle i { color: #f5a623; }
.bar-toggle i.fa-trash-restore,
.bar-toggle i.fa-undo { color: inherit; }
</style>