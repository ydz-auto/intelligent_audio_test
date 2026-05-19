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
      :tags="tags"
      :pagination-info="paginationInfo"
      :is-loading="isLoading"
      @delete-group="handleDeleteGroup"
      @delete-test-case="handleDeleteTestCase"
      @open-add-modal="openAddTestCaseModal"
      @open-edit-modal="handleOpenEditModal"
      @open-create-group-modal="openCreateGroupModal"
      @open-edit-group-modal="openEditGroupModal"
      @open-import-modal="openImportTestCaseModal"
      @open-export-modal="openExportTestCaseModal"
    />
  </div>
</template>

<script setup lang="ts">
import TestCaseListContainer from '../components/common/test-case/TestCaseListContainer.vue';
import { useTestCaseManager } from './TestCaseManagerLogic/testCaseManager';

const {
  testCaseGroups,
  tags,
  paginationInfo,
  isLoading,
  handleDeleteGroup,
  handleDeleteTestCase,
  openAddTestCaseModal,
  handleOpenEditModal,
  openCreateGroupModal,
  openEditGroupModal,
  openImportTestCaseModal,
  openExportTestCaseModal
} = useTestCaseManager();
</script>

<style>
@import '../assets/styles/main.css';
</style>

<style scoped>
.test-case-manager {
  padding: 20px;
  background-color: var(--background-primary);
  min-height: 100vh;
}
</style>