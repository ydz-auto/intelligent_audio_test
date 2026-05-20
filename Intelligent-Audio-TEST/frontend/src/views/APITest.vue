<template>
  <div class="test-view-common">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-exchange-alt"></i>
          API测试
        </h2>
        <p class="page-description">测试语音服务API的功能和性能，验证接口响应和数据正确性</p>
      </div>
    </div>

    <!-- 进度导航 - 使用公共组件 -->
    <ProgressNav 
      :current-step="currentStep" 
      :step-labels="['选择算法', '选择测试用例', '选择被测API', '执行测试', '查看结果']" 
      :step2-tooltip="'选择要测试的API端点'"
      @go-to-step="goToStep"
    />

    <!-- 步骤内容区域 -->
    <div class="step-content">
      <!-- 步骤0：选择算法 -->
      <TestStepContainer
        :is-active="currentStep === 0"
        panel-id="api-step0"
        title="选择算法"
        next-label="下一步"
        :show-prev="false"
        @next="nextStep"
      >
        <template #header-extra>
          <div class="algorithm-toolbar">
            <button class="btn btn-primary" @click="openAlgorithmModal">
              <i class="fas fa-plus"></i> 新增算法
            </button>
            <div class="search-box">
              <i class="fas fa-search search-icon"></i>
              <input type="text" class="search-input" placeholder="搜索算法名称..." v-model="algorithmSearchQuery">
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
        panel-id="api-step1"
        :show-prev="false"
        next-label="下一步"
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
        />
      </TestStepContainer>

      <!-- 步骤2：选择被测API -->
      <TestStepContainer
        :is-active="currentStep === 2"
        panel-id="api-step2"
        title="选择被测API"
        next-label="开始任务"
        @prev="prevStep"
        @next="handleStartTask"
      >
        <template #header-extra>
          <div class="device-toolbar">
            <button class="btn btn-primary" @click="() => openApiEditModal()">
              <i class="fas fa-plus"></i> 新增API
            </button>
            <div class="search-box">
              <i class="fas fa-search search-icon"></i>
              <input type="text" class="search-input" placeholder="搜索API名称或端点..."
                     v-model="apiSearchQuery">
            </div>
            <div class="filter-select">
              <select class="form-input" v-model="apiFilter">
                <option value="all">所有状态</option>
                <option value="online">在线</option>
                <option value="offline">离线</option>
              </select>
            </div>
          </div>
        </template>
        
        <ResourceSelectionGrid
          :items="filteredAPIs"
          :selected-ids="selectedAPIIds"
          :display-fields="apiDisplayFields"
          empty-text="未找到相关API"
          @toggle-selection="toggleAPISelection"
          @action-click="handleResourceAction"
        />
        
        <!-- 分页控件 -->
        <div class="pagination-container" v-if="apiTotalItems > apiPageSize">
          <PaginationComponent
            :current-page="apiCurrentPage"
            :page-size="apiPageSize"
            :total-items="apiTotalItems"
            :total-pages="apiTotalPages"
            @prev-page="handleApiPrevPage"
            @next-page="handleApiNextPage"
            @go-to-page="handleApiPageChange"
            @page-size-change="handleApiPageSizeChange"
          />
        </div>
      </TestStepContainer>

      <!-- 步骤3：执行测试 -->
      <TestStepContainer
        :is-active="currentStep === 3"
        panel-id="api-step3"
        :show-actions="false"
      >
        <TestExecutionComponent
          test-type="API"
          :active-tab="activeTab"
          :task-info="{
            taskName: taskName,
            expectedTotalTime: estimatedTime,
            usedTime: elapsedTime,
            expectedCompleteTime: expectedCompleteTime,
            apiCount: selectedAPIIds.length,
            totalTestCases: totalTestCases,
            concurrentTasks: concurrentTasks,
            testDate: new Date().toLocaleDateString(),
            creator: '系统管理员'
          }"
          :progress-info="{
            totalProgress: progressPercentage,
            completed: completedTests,
            inProgress: inProgressTests,
            pending: pendingTests,
            executionFailed: executionFailedTests,
            evaluationFailed: evaluationFailedTests
          }"
          :api-resources="apiResources"
          :associated-cases="associatedCases"
          :associated-devices="selectedAPIIds.length > 0 ? apis.filter(api => api && selectedAPIIds.map(id => String(id)).includes(String(api.id))) : []"
          :logs="logs"
          :show-logs="true"
          :is-paused="isPaused"
          :is-controlling="isControlling"
          :is-executing="isExecuting"
          @prev-step="prevStep"
          @pause-test="pauseTest"
          @resume-test="resumeTest"
          @stop-test="stopTest"
          @test-case-click="showTestCaseDetails"
          @update:active-tab="newTab => activeTab = newTab"
        />
      </TestStepContainer>

      <!-- 步骤4：查看结果 -->
      <TestStepContainer
        :is-active="currentStep === 4"
        panel-id="api-step4"
        title="测试结果"
        :show-actions="false"
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
          <button class="btn btn-primary" @click="exportResults('pdf')">
            <i class="fas fa-download"></i> 导出报告
          </button>
          <button class="btn btn-success" @click="publishReport">
            <i class="fas fa-paper-plane"></i> 发布
          </button>
          <button class="btn btn-secondary" @click="startNewTest">开始新测试</button>
        </div>

        <!-- 浮动操作按钮区域 -->
        <div id="api-floating-report-actions">
          <button class="btn btn-primary" @click="saveReport">
            <i class="fas fa-save"></i> 保存
          </button>
          <button class="btn btn-success" @click="publishReport">
            <i class="fas fa-paper-plane"></i> 发布
          </button>
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
          v-model="localTaskName"
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

  <!-- 算法配置模态窗 -->
  <AlgorithmConfigModal
    v-model:visible="algorithmModalVisible"
    :mode="editingAlgorithm ? 'edit' : 'list'"
    :edit-data="editingAlgorithm"
  />
</template>

<script setup lang="ts">
import { onMounted, computed, ref } from 'vue'
import { useApiTest } from './APITestLogic/apiTest'
import { useAlgorithmConfig } from '../composables/useAlgorithmConfig'

import ProgressNav from '../components/ProgressNav.vue'
import TestCaseListContainer from '../components/common/test-case/TestCaseListContainer.vue'
import TestExecutionComponent from '../components/TestExecutionComponent.vue'
import TestStepContainer from '../components/common/TestStepContainer.vue'
import ResourceSelectionGrid from '../components/common/ResourceSelectionGrid.vue'
import BasicModal from '../components/common/modal/BasicModal.vue'
import PaginationComponent from '../components/common/PaginationComponent.vue'
import AlgorithmConfigModal from '../components/algorithm/AlgorithmConfigModal.vue'
import AlgorithmSelectionPanel from '../components/algorithm/AlgorithmSelectionPanel.vue'

// 导入报告相关组件
import ComparisonTableComponent from '../components/report/ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from '../components/report/CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from '../components/report/CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from '../components/report/SpecificCaseComparisonComponent.vue'
import TaskReportPanel from '../components/report/TaskReportPanel.vue'

// 模态窗相关状态
const showTaskNameModal = ref(false)
const localTaskName = ref('')

const {
  // 状态
  currentStep,
  apis,
  apiSearchQuery,
  apiFilter,
  selectedAPIIds,
  selectedTestCaseIds,
  activeTab,
  taskName,
  concurrentTasks,
  currentTaskId,
  isPaused,
  isControlling,
  isExecuting,
  executionProgress,
  report,
  isEditingReport,
  
  // 算法相关
  algorithmList,
  filteredAlgorithmList,
  algorithmSearchQuery,
  algorithmModalVisible,
  editingAlgorithm,
  selectedAlgorithmType,
  loadAlgorithms,
  selectAlgorithm,
  getAlgorithmName,
  openAlgorithmModal,
  openAlgorithmConfigModal,
  closeAlgorithmModal,
  
  // 计算属性
  filteredAPIs,
  
  // API分页相关
  apiCurrentPage,
  apiPageSize,
  apiTotalItems,
  apiTotalPages,
  handleApiPageChange,
  handleApiPageSizeChange,
  handleApiPrevPage,
  handleApiNextPage,
  
  deviceApiComparisonData,
  caseExecutionData,
  analysisContent,
  
  // 进度相关
  progressPercentage,
  completedTests,
  inProgressTests,
  pendingTests,
  executionFailedTests,
  evaluationFailedTests,
  totalTestCases,
  taskStatus,
  elapsedTime,
  estimatedTime,
  expectedCompleteTime,
  logs,
  associatedCases,
  apiResources,
  
  // 测试用例 Store 状态
  testCaseGroups,
  tags,
  isLoading,
  
  formData,
  groupFormData,
  editingTestCase,
  editingGroup,
  
  initAPITest,
  nextStep,
  prevStep,
  goToStep,
  updateSelectedCases,
  toggleAPISelection,
  openAPIEditModal: openApiEditModal,
  deleteAPI: deleteApi,
  testAPI: testApi,
  showAPIDetails: showApiDetails,
  editAPI: editApi,
  pauseTest,
  stopTest,
  resumeTest,
  showTestCaseDetails,
  toggleEditReport,
  cancelEditReport,
  handleDeleteGroup,
  handleDeleteTestCase,
  openAddTestCaseModal,
  handleOpenEditModal,
  openCreateGroupModal,
  openEditGroupModal,
  openImportTestCaseModal,
  openExportTestCaseModal,
  publishReport,
  saveReport,
  toggleEditConclusion,
  exportResults,
  skipTestCase,
  removeTestCase,
  startNewTest,
  
  // 常量/列定义
  deviceAPIColumns: deviceApiColumns,
  caseExecutionColumns
} = useApiTest()

// 处理开始任务按钮点击
const handleStartTask = () => {
  // 重置任务名称
  localTaskName.value = `API测试任务_${new Date().toLocaleString()}`
  // 显示编辑任务名称模态窗
  showTaskNameModal.value = true
}

// 确认任务名称并开始测试
const confirmTaskName = () => {
  // 隐藏模态窗
  showTaskNameModal.value = false
  // 将用户编辑的任务名称传递给从 useApiTest() 中解构出来的 taskName
  taskName.value = localTaskName.value
  // 跳转到下一步（执行测试）
  nextStep()
}

// API显示字段配置
const apiDisplayFields = [
  { key: 'apiUrl', label: '端点' },
  { key: 'description', label: '描述' }
]

// 算法显示字段配置
const algorithmDisplayFields = [
  { key: 'type', label: '类型' },
  { key: 'name', label: '名称' }
]

// 处理资源操作点击
const handleResourceAction = ({ actionId, itemId }: { actionId: string; itemId: string | number }) => {
  switch (actionId) {
    case 'test':
      testApi(itemId)
      break
    case 'edit':
      editApi(itemId)
      break
    case 'delete':
      deleteApi(itemId)
      break
  }
}

// 设备信息对比相关数据
const deviceInfoColumns = [
  { key: 'name', label: '名称', type: 'text', sortable: true },
  { key: 'type', label: '类型', type: 'text', sortable: true },
  { key: 'version', label: '版本', type: 'text', sortable: true },
  { key: 'status', label: '状态', type: 'status', sortable: true },
  { key: 'totalCases', label: '总用例数', type: 'number', sortable: true },
  { key: 'completedCases', label: '已完成用例数', type: 'number', sortable: true },
  { key: 'failedCases', label: '失败用例数', type: 'number', sortable: true },
  { key: 'successRate', label: '成功率(%)', type: 'number', sortable: true },
  { key: 'avgResponseTime', label: '平均响应时间(ms)', type: 'number', sortable: true },
  { key: 'stability', label: '稳定性(%)', type: 'number', sortable: true }
]

const deviceInfoData = computed(() => deviceApiComparisonData.value)

// 整合报告表格数据
const reportTables = computed(() => [
  {
    title: '设备/API信息对比',
    columns: deviceInfoColumns,
    data: deviceInfoData.value,
    defaultCollapsed: true
  },
  {
    title: '用例执行数量对比',
    columns: caseExecutionColumns,
    data: caseExecutionData.value,
    defaultCollapsed: true
  }
])

// 组件挂载时初始化
onMounted(() => {
  initAPITest()
})
</script>

<style>
@import '../assets/styles/main.css';
@import '../assets/styles/test-common.css';
</style>

<style scoped>
@import '../assets/styles/apiTest.css';
</style>
