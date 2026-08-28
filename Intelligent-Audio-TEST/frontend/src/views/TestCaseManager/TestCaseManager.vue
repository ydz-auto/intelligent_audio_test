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
    
    <TestCaseListContainer
      :test-case-groups="testCaseGroups"
      :tag-view-data="tagViewData"
      :tags="tags"
      :tag-view-pagination="tagViewPagination"
      :tag-view-loading="tagViewLoading"
      :pagination-info="paginationInfo"
      :is-loading="isLoading"
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
    />
  </div>
</template>

<script setup lang="ts">
import TestCaseListContainer from '../../components/common/test-case/TestCaseListContainer.vue';
import { useTestCaseManager } from './testCaseManager';

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
  loadMoreTagView
} = useTestCaseManager();
</script>

<style>
@import '../../assets/styles/main.css';
</style>

<style scoped>
.test-case-manager {
  padding: 20px;
  background-color: var(--background-primary);
  min-height: 100vh;
}
</style>