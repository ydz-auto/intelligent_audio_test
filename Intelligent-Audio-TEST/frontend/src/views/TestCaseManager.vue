<template>
  <div class="test-case-manager">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-tasks"></i>
          测试用例管理
        </h2>
        <p class="page-description">统一管理端到端测试用例和API测试用例</p>
      </div>
    </div>
    
    <!-- 测试用例列表容器 -->
  <TestCaseListContainer
    :test-case-groups="testCaseGroups"
    :tags="tags"
    :pagination-info="paginationInfo"
    :show-test-case-modal="showTestCaseModal"
    :show-group-modal="showGroupModal"
    :show-import-modal="showImportModal"
    :show-export-modal="showExportModal"
    :form-data="formData"
    :group-form-data="groupFormData"
    :editing-test-case="editingTestCase"
    :editing-group="editingGroup"
    :is-loading="isLoading"
    @delete-group="handleDeleteGroup"
    @delete-test-case="handleDeleteTestCase"
    @open-add-modal="openAddTestCaseModal"
    @open-edit-modal="handleOpenEditModal"
    @open-create-group-modal="openCreateGroupModal"
    @open-edit-group-modal="openEditGroupModal"
    @open-import-modal="openImportTestCaseModal"
    @open-export-modal="openExportTestCaseModal"
    @close-modal="handleModalClose"
    @save-modal="handleSaveModal"
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
  showTestCaseModal,
  showGroupModal,
  showImportModal,
  showExportModal,
  formData,
  groupFormData,
  editingTestCase,
  editingGroup,
  isLoading,
  handleDeleteGroup,
  handleDeleteTestCase,
  openAddTestCaseModal,
  handleOpenEditModal,
  openCreateGroupModal,
  openEditGroupModal,
  openImportTestCaseModal,
  openExportTestCaseModal,
  handleModalClose,
  handleSaveModal
} = useTestCaseManager();

// Debug: Check testCaseGroups
import { watch } from 'vue';
watch(testCaseGroups, (newValue) => {
  console.log('[TestCaseManager] testCaseGroups changed:', newValue);
  console.log('[TestCaseManager] testCaseGroups keys:', Object.keys(newValue));
}, { deep: true, immediate: true });
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
