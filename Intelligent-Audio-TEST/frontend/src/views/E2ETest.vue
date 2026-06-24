<template>
  <div class="test-view-common">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-project-diagram"></i>
          端到端测试
        </h2>
        <p class="page-description">通过完整的测试流程验证语音产品的功能和性能</p>
      </div>
    </div>

    <!-- 进度导航 - 使用公共组件 -->
    <ProgressNav 
      :current-step="currentStep" 
      :step-labels="['选择算法', '选择测试用例', '选择测试设备', '执行测试', '查看结果']" 
      :step2-tooltip="'选择要使用的测试设备'"
      @go-to-step="goToStep"
    />

    <!-- 步骤内容区域 -->
    <div class="step-content">
      <!-- 步骤0：选择算法 -->
      <TestStepContainer
        :is-active="currentStep === 0"
        panel-id="e2e-step0"
        title="选择算法"
        next-label="下一步"
        :show-prev="false"
        @next="nextStep"
      >
        <template #header-extra>
          <div class="algorithm-toolbar">
            <button class="btn btn-primary" @click="openCreateAlgorithmModal">
              <i class="fas fa-plus"></i> 新增算法
            </button>
            <div class="search-box">
              <i class="fas fa-search search-icon"></i>
              <input type="text" class="search-input" placeholder="搜索算法名称..." v-model="algorithmSearchQuery" @input="searchAlgorithms">
            </div>
          </div>
        </template>

        <AlgorithmSelectionPanel
          :algorithm-list="algorithmList"
          :selected-algorithm-type="selectedAlgorithmType"
          :search-query="algorithmSearchQuery"
          @select="selectAlgorithm"
          @open-config="openAlgorithmConfigModal"
        />
      </TestStepContainer>

      <!-- 步骤1：选择测试用例 -->
      <TestStepContainer
        :is-active="currentStep === 1"
        panel-id="e2e-step1"
        :show-prev="false"
        @next="nextStep"
      >
        <TestCaseListContainer 
          :test-case-groups="testCaseGroups"
          :tags="tags"
          :algorithm-type-filter="selectedAlgorithmType || 'all'"
          :is-loading="isLoading || false"
          @delete-group="handleDeleteGroup"
          @delete-test-case="handleDeleteTestCase"
          @open-add-modal="openAddTestCaseModal"
          @open-edit-modal="handleOpenEditModal"
          @open-create-group-modal="openCreateGroupModal"
          @open-edit-group-modal="openEditGroupModal"
          @open-import-modal="openImportTestCaseModal"
          @open-export-modal="openExportTestCaseModal"
          @updateSelectedCases="updateSelectedCases"
          @update-selected-groups="updateSelectedGroups"
        />
      </TestStepContainer>

      <!-- 步骤2：选择测试设备 -->
      <TestStepContainer
        :is-active="currentStep === 2"
        panel-id="e2e-step2"
        title="选择测试设备"
        next-label="开始任务"
        @prev="prevStep"
        @next="handleStartTask"
      >
        <template #header-extra>
          <div class="device-toolbar">
            <button class="btn btn-primary" @click="handleAddDevice">
              <i class="fas fa-plus"></i> 新增设备
            </button>
            <button class="btn btn-secondary" @click.stop="scanDevices('test')">
              <i class="fas fa-search"></i> 扫描设备
            </button>
            <div class="search-box">
              <i class="fas fa-search search-icon"></i>
              <input type="text" class="search-input" placeholder="搜索设备名称或型号..." v-model="deviceSearchQuery" @input="searchDevices">
            </div>
            <div class="filter-select">
              <select class="form-input" v-model="selectedDeviceStatus" @change="filterDevices">
                <option value="all">所有状态</option>
                <option value="online">在线</option>
                <option value="offline">离线</option>
              </select>
            </div>
          </div>
        </template>

        <ResourceSelectionGrid
          :items="algorithmFilteredDevices"
          :selected-ids="selectedDeviceIdsList"
          :display-fields="deviceDisplayFields"
          empty-text="未找到相关设备"
          @toggle-selection="handleToggleDeviceSelection"
          @action-click="handleResourceAction"
        />
        
        <!-- 分页控件 -->
        <div class="pagination-container" v-if="totalItems > pageSize">
          <PaginationComponent
            :current-page="currentPage"
            :page-size="pageSize"
            :total-items="totalItems"
            :total-pages="totalPages"
            @prev-page="handlePrevPage"
            @next-page="handleNextPage"
            @go-to-page="handlePageChange"
            @page-size-change="handlePageSizeChange"
          />
        </div>
      </TestStepContainer>

      <!-- 步骤3：执行测试 -->
      <TestStepContainer
        :is-active="currentStep === 3"
        panel-id="e2e-step3"
        :show-actions="false"
      >
        <TestExecutionComponent
          test-type="E2E"
          :task-info="{
            taskName: 'E2E测试任务',
            expectedTotalTime: estimatedTime,
            usedTime: elapsedTime,
            expectedCompleteTime: expectedCompleteTime,
            deviceCount: associatedDevices.length,
            totalTestCases: totalTestCases || 0,
            concurrentTasks: concurrentTasks,
            testDate: new Date().toLocaleDateString(),
            creator: '系统管理员'
          }"
          :progress-info="{
            totalProgress: progressPercentage || 0,
            completed: completedTests || 0,
            inProgress: inProgressTests || 0,
            pending: pendingTests || 0,
            executionFailed: executionFailedTests || 0,
            evaluationFailed: evaluationFailedTests || 0
          }"
          :associated-cases="associatedCases"
          :associated-devices="associatedDevices"
          :test-progress="testProgress"
          :logs="logs"
          :show-logs="true"
          :active-tab="activeTab"
          @update:active-tab="newTab => activeTab = newTab"
          :is-paused="isPaused"
          :is-controlling="isControlling"
          :is-executing="isExecuting"
          @prev-step="prevStep"
          @pause-test="pauseTest"
          @resume-test="resumeTest"
          @stop-test="stopTest"
          @test-case-click="showTestCaseDetails"
        />
      </TestStepContainer>

      <!-- 步骤4：查看结果 -->
      <TestStepContainer
        :is-active="currentStep === 4"
        panel-id="e2e-step4"
        title="测试结果"
        :show-actions="false"
        custom-class="report-step"
      >
        <!-- 任务报告区域 -->
        <TaskReportPanel 
          :report="report"
          :is-editing-report="isEditingReport"
          :is-editing-conclusion="isEditingConclusion"
          :analysis-content="analysisContent"
          :tables="reportTables"
          @toggle-edit="toggleEditReport"
          @save-report="saveReport"
          @cancel-edit="cancelEditReport"
          @toggle-conclusion-edit="toggleEditConclusion"
          @save-conclusion="saveConclusion"
          @cancel-conclusion="cancelEditConclusion"
        />

        <!-- 操作按钮区域 -->
        <div class="step-actions">
          <button class="btn btn-secondary" @click="prevStep">
            <i class="fas fa-arrow-left"></i> 上一步
          </button>
          <button class="btn btn-primary" @click="saveReport">
            <i class="fas fa-save"></i> 保存报告
          </button>
          <button class="btn btn-primary" @click="exportResults('pdf')">
            <i class="fas fa-download"></i> 导出报告
          </button>
          <button class="btn btn-success" @click="publishReport">
            <i class="fas fa-paper-plane"></i> 发布
          </button>
          <button class="btn btn-secondary" @click="startNewTest">开始新测试</button>
        </div>
      </TestStepContainer>
    </div>
  </div>

  <!-- 编辑任务名称模态窗 -->
  <BasicModal
    :visible="showTaskNameModal"
    title="编辑任务名称"
    width="400px"
    @close="showTaskNameModal = false"
    @cancel="showTaskNameModal = false"
    @confirm="confirmTaskName"
  >
    <div class="task-name-modal">
      <div class="form-group">
        <label for="task-name-input">任务名称</label>
        <input
          type="text"
          id="task-name-input"
          class="form-input"
          v-model="taskName"
          placeholder="请输入任务名称"
          maxlength="50"
          autofocus
        />
      </div>
      <div class="form-hint">
        <small>请输入一个描述性的任务名称，便于后续查看测试结果</small>
      </div>
    </div>
  </BasicModal>

  <!-- 移除直接添加的TestCaseModal，改用TestCaseListContainer内部的模态框 -->

  <!-- 算法配置模态窗 -->
  <AlgorithmConfigModal
    v-model:visible="algorithmModalVisible"
    :mode="algorithmModalMode"
    :edit-data="algorithmEditData"
  />
</template>

<script setup lang="ts">
// 导入Vue组合式API
import { onMounted, onUnmounted, ref } from 'vue'

// 导入E2E测试逻辑组合式函数
import { useE2eView } from '../composables/useE2eView'
import AlgorithmConfigModal from '../components/algorithm/AlgorithmConfigModal.vue'
import AlgorithmSelectionPanel from '../components/algorithm/AlgorithmSelectionPanel.vue'

// 导入公共组件
import ProgressNav from '../components/ProgressNav.vue'
import TestCaseListContainer from '../components/common/test-case/TestCaseListContainer.vue'
import TestExecutionComponent from '../components/TestExecutionComponent.vue'
import TestStepContainer from '../components/common/TestStepContainer.vue'
import ResourceSelectionGrid from '../components/common/ResourceSelectionGrid.vue'
import BasicModal from '../components/common/modal/BasicModal.vue'
import PaginationComponent from '../components/common/PaginationComponent.vue'

// 导入报告相关组件
import TaskReportPanel from '../components/report/TaskReportPanel.vue'

// 模态窗相关状态
const showTaskNameModal = ref(false)

// 使用 E2E 视图逻辑
const {
  // 基础状态
  currentStep,
  selectedTestCaseIds,
  selectedGroupIds,
  taskName,
  activeTab,
  associatedDevices,
  currentTaskId,
  isExecuting,
  isPaused,
  isControlling,
  concurrentTasks,
  isEditingReport,
  report,
  testCaseGroups,
  tags,
  isLoading,
  
  // 进度状态
  progressPercentage,
  completedTests,
  inProgressTests,
  pendingTests,
  executionFailedTests,
  evaluationFailedTests,
  totalTestCases,
  elapsedTime,
  estimatedTime,
  expectedCompleteTime,
  logs,
  associatedCases,
  testProgress,

  formData,
  groupFormData,
  editingTestCase,
  editingGroup,
  
  filteredDevices,
  algorithmFilteredDevices,
  selectedDeviceIdsList,
  deviceDisplayFields,
  analysisContent,
  reportTables,
  deviceSearchQuery,
  selectedDeviceStatus,
  
  // 分页相关
  currentPage,
  pageSize,
  totalItems,
  totalPages,
  handlePageChange,
  handlePageSizeChange,
  handlePrevPage,
  handleNextPage,
  
  // 方法
  goToStep,
  nextStep,
  prevStep,
  handleDeleteGroup,
  handleDeleteTestCase,
  openAddTestCaseModal,
  handleOpenEditModal,
  openCreateGroupModal,
  openEditGroupModal,
  openImportTestCaseModal,
  openExportTestCaseModal,
  updateSelectedCases,
  updateSelectedGroups,
  addDevice,
  scanDevices,
  searchDevices,
  filterDevices,
  handleToggleDeviceSelection,
  handleResourceAction,
  handleAddDevice,
  pauseTest,
  resumeTest,
  stopTest,
  showTestCaseDetails,
  skipTestCase,
  showAddTestCaseModalHandler,
  removeTestCase,
  toggleEditReport,
  saveReport,
  cancelEditReport,
  isEditingConclusion,
  toggleEditConclusion,
  saveConclusion,
  cancelEditConclusion,
  exportResults,
  publishReport,
  startNewTest,
  
  // 算法相关
  algorithmList,
  filteredAlgorithmList,
  selectedAlgorithmType,
  loadAlgorithms,
  selectAlgorithm,
  getAlgorithmName,
  openAlgorithmModal,
  openCreateAlgorithmModal,
  openAlgorithmConfigModal,
  algorithmModalVisible,
  algorithmModalMode,
  algorithmEditData,
  algorithmSearchQuery,
  searchAlgorithms
} = useE2eView()

// 处理开始任务按钮点击
const handleStartTask = () => {
  console.log('[E2ETest] handleStartTask called')
  // 重置任务名称
  taskName.value = `E2E测试任务_${new Date().toLocaleString()}`
  // 显示编辑任务名称模态窗
  showTaskNameModal.value = true
}

// 确认任务名称并开始测试
const confirmTaskName = () => {
  console.log('[E2ETest] confirmTaskName called')
  // 隐藏模态窗
  showTaskNameModal.value = false
  // 跳转到下一步（执行测试）
  nextStep()
  console.log('[E2ETest] confirmTaskName after nextStep')
}
</script>

<style>
@import '../assets/styles/main.css';
@import '../assets/styles/test-common.css';
@import '../assets/styles/e2etest.css';
</style>

<style scoped>
@import '../assets/styles/testCaseManager.css';

/* 设备管理头部 */
.device-management-header {
  margin-bottom: 24px;
}

/* 搜索框样式 */
.search-box {
  position: relative;
  flex: 1;
  max-width: 300px;
}

/* 按钮样式 - 扩展 */
.btn-text {
  background: none;
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
}

.btn-text:hover {
  background-color: rgba(22, 119, 255, 0.1);
}

/* 动画效果 */
@keyframes pulse {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
  100% {
    opacity: 1;
  }
}

/* 信息提示样式 */
.info-alert {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--primary-light);
  border: 1px solid var(--primary-color);
  border-radius: var(--border-radius-md);
  color: var(--primary-color);
  font-size: var(--font-size-sm);
}

.info-alert i {
  font-size: 16px;
}
</style>
