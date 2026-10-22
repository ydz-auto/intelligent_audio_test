<template>
  <div class="test-view-common">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary);">
          <i class="fas fa-play-circle"></i>
          开始测试
        </h2>
        <p class="page-description">选择用例与设备/API，在同一流程内完成语音测试与报告生成</p>
      </div>
      <!-- 全局算法 chip（只读 + ×清空，INT-486 去选算法步骤：算法切换已全局化） -->
      <div v-if="selectedAlgorithmType" class="global-algorithm-chip">
        <i class="fas fa-microchip"></i>
        <span>算法：{{ getAlgorithmName(selectedAlgorithmType) }}</span>
        <button class="chip-clear" title="清空全局算法" @click="clearGlobalAlgorithm">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>

    <!-- 进度导航（四步） -->
    <ProgressNav
      :current-step="currentStep"
      :step-labels="stepLabels"
      :step-count="4"
      :step-tooltips="stepTooltips"
      @go-to-step="goToStep"
    />

    <!-- 步骤内容区域 -->
    <div class="step-content">
      <!-- 步骤0：选择测试用例（不分类型，E2E+API 全量） -->
      <TestStepContainer
        :is-active="currentStep === 0"
        panel-id="test-step0"
        title="选择测试用例"
        next-label="下一步"
        :show-prev="false"
        @next="nextStep"
      >
        <div v-if="stepHints?.caseSelection" class="info-alert">
          <i class="fas fa-info-circle"></i> {{ stepHints.caseSelection }}
        </div>
        <TestCaseListContainer
          :test-case-groups="testCaseGroups"
          :tag-view-data="tagViewData"
          :tags="tags"
          :tag-view-pagination="tagViewPagination"
          :tag-view-loading="tagViewLoading"
          :algorithm-type-filter="selectedAlgorithmType || ViewMode.ALL"
          :test-type-filter="ViewMode.ALL"
          :is-loading="isLoading || false"
          :error="error"
          :tag-view-error="tagViewError"
          @delete-group="handleDeleteGroup"
          @delete-test-case="handleDeleteTestCase"
          @open-add-modal="handleOpenAddModal"
          @open-edit-modal="handleOpenEditModal"
          @open-create-group-modal="openCreateGroupModal"
          @open-edit-group-modal="openEditGroupModal"
          @open-import-modal="openImportTestCaseModal"
          @open-export-modal="openExportTestCaseModal"
          @updateSelectedCases="updateSelectedCases"
          @tag-filter-change="handleTagFilterChange"
          @group-filter-change="handleGroupFilterChange"
          @load-more-tags="loadMoreTagView"
        />
      </TestStepContainer>

      <!-- 步骤1：同屏选设备+API（混合执行） -->
      <TestStepContainer
        :is-active="currentStep === 1"
        panel-id="test-step1"
        title="选择设备/API"
        next-label="开始任务"
        :show-prev="true"
        @prev="prevStep"
        @next="handleStartTask"
      >
        <div v-if="voiceLlmHint" class="info-alert">
          <i class="fas fa-info-circle"></i> {{ voiceLlmHint }}
        </div>

        <!-- 设备区 -->
        <div class="resource-section">
          <div class="section-header">
            <h4><i class="fas fa-mobile-alt"></i> 设备</h4>
            <div class="device-toolbar">
              <button class="btn btn-secondary" @click.stop="scanDevices('test')">
                <i class="fas fa-search"></i> 扫描设备
              </button>
              <button class="btn btn-primary" @click="handleAddResource('device')">
                <i class="fas fa-plus"></i> 新增设备
              </button>
              <div class="search-box">
                <i class="fas fa-search search-icon"></i>
                <input type="text" class="search-input" placeholder="搜索设备名称或型号..." v-model="deviceSearchQuery">
              </div>
              <div class="filter-select">
                <select class="form-input" v-model="selectedDeviceStatus">
                  <option :value="ViewMode.ALL">所有状态</option>
                  <option :value="DeviceStatus.ONLINE">在线</option>
                  <option :value="DeviceStatus.OFFLINE">离线</option>
                </select>
              </div>
            </div>
          </div>

          <ResourceSelectionGrid
            :items="algorithmFilteredDevices"
            :selected-ids="selectedDeviceIds"
            :display-fields="deviceDisplayFields"
            :empty-text="'未找到相关设备'"
            :get-target-mode="getDeviceTargetMode"
            :on-target-mode-change="setDeviceTargetMode"
            @toggle-selection="(id) => toggleResourceSelection(id, 'device')"
            @action-click="(e) => handleResourceAction(e, 'device')"
          />

          <!-- 设备分页 -->
          <div class="pagination-container" v-if="deviceTotalItems > devicePageSize">
            <PaginationComponent
              :current-page="deviceCurrentPage"
              :page-size="devicePageSize"
              :total-items="deviceTotalItems"
              :total-pages="deviceTotalPages"
              @prev-page="handleDevicePrevPage"
              @next-page="handleDeviceNextPage"
              @go-to-page="handleDevicePageChange"
              @page-size-change="handleDevicePageSizeChange"
            />
          </div>
        </div>

        <!-- 被测 API 区 -->
        <div class="resource-section">
          <div class="section-header">
            <h4><i class="fas fa-server"></i> 被测 API</h4>
            <div class="device-toolbar">
              <button class="btn btn-primary" @click="handleAddResource('api')">
                <i class="fas fa-plus"></i> 新增API
              </button>
              <div class="search-box">
                <i class="fas fa-search search-icon"></i>
                <input type="text" class="search-input" placeholder="搜索API名称或端点..." v-model="apiSearchQuery">
              </div>
              <div class="filter-select">
                <select class="form-input" v-model="apiFilter">
                  <option :value="ViewMode.ALL">所有状态</option>
                  <option :value="ApiEndpointStatus.ONLINE">在线</option>
                  <option :value="ApiEndpointStatus.OFFLINE">离线</option>
                </select>
              </div>
            </div>
          </div>

          <ResourceSelectionGrid
            :items="filteredAPIs"
            :selected-ids="selectedAPIIds"
            :display-fields="apiDisplayFields"
            :empty-text="'未找到相关API'"
            :get-target-mode="getApiTargetMode"
            :on-target-mode-change="setApiTargetMode"
            @toggle-selection="(id) => toggleResourceSelection(id, 'api')"
            @action-click="(e) => handleResourceAction(e, 'api')"
          />

          <!-- API 分页 -->
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
        </div>

        <!-- INT-1268/INT-1115：底部双道并行/串行示意图（随卡片选项实时渲染） -->
        <ExecutionDiagram :lanes="executionLanes" :empty="executionDiagramEmpty" />
      </TestStepContainer>

      <!-- 步骤2：执行测试（混合） -->
      <TestStepContainer
        :is-active="currentStep === 2"
        panel-id="test-step2"
        :show-actions="false"
      >
        <TestExecutionComponent
          test-type="混合"
          :active-tab="activeTab"
          :task-status="taskStatus"
          :execution-status="taskExecutionStatus"
          :evaluation-status="taskEvaluationStatus"
          :task-info="{
            taskName: taskName,
            expectedTotalTime: estimatedTime,
            usedTime: elapsedTime,
            expectedCompleteTime: expectedCompleteTime,
            deviceCount: selectedDeviceIds.length,
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
          :associated-devices="associatedDevices"
          :logs="logs"
          :show-logs="true"
          :is-paused="isPaused"
          :is-controlling="isControlling"
          :is-executing="isExecuting"
          :connection-fallback="isProgressPolling"
          @prev-step="prevStep"
          @pause-test="pauseTest"
          @resume-test="resumeTest"
          @stop-test="stopTest"
          @test-case-click="showTestCaseDetails"
          @update:active-tab="newTab => activeTab = newTab"
        />
      </TestStepContainer>

      <!-- 步骤3：查看结果 -->
      <TestStepContainer
        :is-active="currentStep === 3"
        panel-id="test-step3"
        title="测试结果"
        :show-actions="false"
        custom-class="report-step"
      >
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
          <button class="btn btn-secondary" @click="startNewTest">
            <i class="fas fa-redo"></i> 开始新测试
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
        <small>已选 {{ selectedDeviceIds.length }} 台设备 · {{ selectedAPIIds.length }} 个 API<template v-if="serialCount > 0"> · 串行 {{ serialCount }} 个目标</template></small>
      </div>
      <div class="form-hint">
        <small>请输入一个描述性的任务名称，便于后续查看测试结果</small>
      </div>
      <div class="form-group">
        <label>可见性</label>
        <VisibilitySelector :model-value="taskVisibility" @change="handleVisibilityChange" />
      </div>
    </div>
  </BasicModal>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'
import "../../assets/styles/e2etest/dropdown.css"
import "../../assets/styles/e2etest/e2etest.css"
import { ref, computed } from 'vue'
import { ViewMode, DeviceStatus, ApiEndpointStatus } from '@/domain/enums'
import type { ExecutionMode } from '@/domain'
import { useMergedTestFlow } from '../../composables/shared/useMergedTestFlow'
import ProgressNav from '../../components/layout/ProgressNav.vue'
import TestCaseListContainer from '../../components/common/test-case/TestCaseListContainer.vue'
import TestExecutionComponent from '../../components/layout/TestExecutionComponent.vue'
import TestStepContainer from '../../components/common/misc/TestStepContainer.vue'
import ResourceSelectionGrid from '../../components/common/data/ResourceSelectionGrid.vue'
import ExecutionDiagram from '../../components/common/data/ExecutionDiagram.vue'
import BasicModal from '../../components/common/modal/BasicModal.vue'
import VisibilitySelector from '../../components/common/visibility/VisibilitySelector.vue'
import PaginationComponent from '../../components/common/data/PaginationComponent.vue'
import TaskReportPanel from '../../components/report/TaskReportPanel.vue'

const flow = useMergedTestFlow()

// 解构所需状态/方法
const {
  currentStep, steps, taskName, activeTab, concurrentTasks,
  taskVisibility, handleVisibilityChange,
  selectedTestCaseIds, currentTaskId,
  globalAlgorithm, algorithmList, selectedAlgorithmType, getAlgorithmName,
  testCaseGroups, tags, tagViewData, tagViewPagination, tagViewLoading, isLoading, error, tagViewError,
  fetchTagView, loadMoreTagView, handleTagFilterChange, handleGroupFilterChange,
  handleDeleteGroup, handleDeleteTestCase, handleSaveModal,
  handleOpenAddModal, handleOpenEditModal,
  openCreateGroupModal, openEditGroupModal, openImportTestCaseModal, openExportTestCaseModal,
  updateSelectedCases, showTestCaseDetails,
  deviceManagement, algorithmFilteredDevices,
  associatedDevices, selectedDeviceIds,
  apis, apiSearchQuery, apiFilter, selectedAPIIds, filteredAPIs, allFilteredAPIs,
  apiCurrentPage, apiPageSize, apiTotalItems, apiTotalPages,
  handleApiPageChange, handleApiPageSizeChange, handleApiPrevPage, handleApiNextPage,
  toggleAPISelection, openAPIEditModal, deleteAPI, testAPI, editAPI, loadAPIs,
  toggleResourceSelection, handleResourceAction, handleAddResource, scanDevices,
  getTargetMode, setTargetMode, serialCount, executionLanes, executionDiagramEmpty,
  isExecuting, executionProgress, isPaused, isControlling, pauseTest, resumeTest, stopTest,
  progressPercentage, completedTests, inProgressTests, pendingTests,
  executionFailedTests, evaluationFailedTests, totalTestCases, taskStatus,
  taskExecutionStatus, taskEvaluationStatus,
  elapsedTime, estimatedTime, expectedCompleteTime, logs, associatedCases,
  apiResources, isProgressPolling, canStartTest,
  startMergedTask,
  report, isEditingReport, isEditingConclusion, analysisContent, reportTables,
  deviceApiComparisonData, caseExecutionData, deviceApiColumns, caseExecutionColumns,
  toggleEditReport, saveReport, cancelEditReport, toggleEditConclusion,
  cancelEditConclusion, saveConclusion, exportResults, publishReport, startNewTest,
  isVoiceLLM, voiceLlmHint, stepHints,
  goToStep, nextStep, prevStep,
  initTest,
} = flow

// INT-1268/INT-1115：逐卡「并行/串行」受控绑定（卡片受控值 / 载荷 / 示意图同源）
const getDeviceTargetMode = (id: string | number): ExecutionMode => getTargetMode('device', id)
const setDeviceTargetMode = (id: string | number, mode: ExecutionMode) => setTargetMode('device', id, mode)
const getApiTargetMode = (id: string | number): ExecutionMode => getTargetMode('api', id)
const setApiTargetMode = (id: string | number, mode: ExecutionMode) => setTargetMode('api', id, mode)

// 步骤标签（合并流程四步）
const stepLabels = computed(() => [
  '选择测试用例',
  '选择设备/API',
  '执行测试',
  '查看结果',
])

// 步骤 tooltips（四步独立数组，与 stepLabels 一一对应，ProgressNav 不按 index 特判）
const stepTooltips = [
  '选择要执行的测试用例和配置参数',
  '选择要测试的测试设备或被测 API（同屏混合选择）',
  '运行测试并实时监控执行进度',
  '查看和导出测试报告',
]

// 资源显示字段
const deviceDisplayFields = [
  { label: '设备名称', key: 'name' },
  { label: '型号', key: 'model' },
  { label: '序列号', key: 'serialNumber' },
  { label: '状态', key: 'status', isStatus: true },
]
const apiDisplayFields = [
  { key: 'apiUrl', label: '端点' },
  { key: 'description', label: '描述' },
]

// 设备分页（从 deviceManagement 透传）
const deviceCurrentPage = computed(() => deviceManagement.currentPage.value)
const devicePageSize = computed(() => deviceManagement.pageSize.value)
const deviceTotalItems = computed(() => deviceManagement.totalItems.value)
const deviceTotalPages = computed(() => deviceManagement.totalPages.value)
const handleDevicePageChange = (page: number) => deviceManagement.handlePageChange(page)
const handleDevicePageSizeChange = (size: number) => deviceManagement.handlePageSizeChange(size)
const handleDevicePrevPage = () => deviceManagement.handlePrevPage()
const handleDeviceNextPage = () => deviceManagement.handleNextPage()
const deviceSearchQuery = deviceManagement.deviceSearchQuery
const selectedDeviceStatus = deviceManagement.selectedDeviceStatus

// ============ 任务名称模态窗 ============
const showTaskNameModal = ref(false)
const localTaskName = ref('')

const handleStartTask = () => {
  localTaskName.value = `测试任务_${new Date().toLocaleString()}`
  showTaskNameModal.value = true
}

const confirmTaskName = async () => {
  showTaskNameModal.value = false
  ;(taskName as any).value = localTaskName.value
  await nextStep()
}

// 清空全局算法（chip ×）
const clearGlobalAlgorithm = () => {
  globalAlgorithm.clear()
}
</script>

<style scoped>

.device-toolbar{
margin-bottom: 20px;
padding: 16px;
background: linear-gradient(135deg, var(--card) 0%, var(--muted) 100%);
border-radius: var(--radius-lg);
box-shadow: var(--shadow-sm);
border: 1px solid var(--gray-light);
}

.section-header{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md, 16px);
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.section-header h4{
  margin: 0;
  font-size: 16px;
  font-weight: var(--font-weight-semibold, 600);
  color: var(--foreground);
  display: flex;
  align-items: center;
  gap: 8px;
}

.resource-section{
  margin-bottom: 24px;
}

.info-alert{
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  padding: var(--spacing-sm, 8px) var(--spacing-md, 16px);
  background: var(--accent, var(--secondary-light));
  border: 1px solid var(--primary, var(--secondary));
  border-radius: var(--radius-md);
  color: var(--primary, var(--secondary));
  font-size: var(--font-size-sm, 13px);
  margin-bottom: var(--spacing-md, 16px);
}

.info-alert i{
  font-size: 16px;
}

/* 全局算法 chip（只读 + ×清空） */
.global-algorithm-chip{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  border: 1px solid var(--primary);
  border-radius: var(--radius-full);
  color: var(--primary);
  font-size: 13px;
  font-weight: 500;
}

.global-algorithm-chip .chip-clear{
  background: none;
  border: none;
  color: var(--primary);
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  opacity: 0.7;
}

.global-algorithm-chip .chip-clear:hover{
  opacity: 1;
}

/* step-content - 自全局样式就近迁移（语义 token，深浅两套成立） */
.step-content{
background-color: var(--card);
border-radius: var(--radius-lg);
box-shadow: var(--shadow-sm);
padding: 24px;
margin-top: 24px;
}

.test-view-common .step-content{
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
}

/* 步骤面板底沿用语义 token（覆盖 TestStepContainer 硬编码 white，INT-737 深浅两套） */
:deep(.step-panel.active){
  background: var(--card);
}

/* 资源卡底沿用语义 token（覆盖 ResourceSelectionGrid 硬编码 white） */
:deep(.resource-card){
  background: var(--card);
}

:deep(.resource-card.selected .resource-select-btn){
  background: var(--primary);
  color: var(--primary-foreground);
  border-color: var(--primary);
}
</style>
