<template>
  <div class="test-view-common">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i :class="pageTitleIcon"></i>
          {{ pageTitle }}
        </h2>
        <p class="page-description">{{ pageDescription }}</p>
      </div>
    </div>

    <!-- 进度导航 -->
    <ProgressNav
      :current-step="currentStep"
      :step-labels="stepLabels"
      :step2-tooltip="step2Tooltip"
      @go-to-step="goToStep"
    />

    <!-- 步骤内容区域 -->
    <div class="step-content">
      <!-- 步骤0：选择算法 -->
      <TestStepContainer
        :is-active="currentStep === 0"
        panel-id="test-step0"
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
        panel-id="test-step1"
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
          :algorithm-type-filter="selectedAlgorithmType || 'all'"
          :test-type-filter="testType"
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
          @tag-filter-change="handleTagFilterChange"
          @group-filter-change="handleGroupFilterChange"
          @load-more-tags="loadMoreTagView"
        />
      </TestStepContainer>

      <!-- 步骤2：选择资源（设备/API） -->
      <TestStepContainer
        :is-active="currentStep === 2"
        panel-id="test-step2"
        :title="step2Title"
        next-label="开始任务"
        @prev="prevStep"
        @next="handleStartTask"
      >
        <template #header-extra>
          <div class="device-toolbar">
            <button class="btn btn-primary" @click="handleAddResource">
              <i class="fas fa-plus"></i> {{ addResourceLabel }}
            </button>
            <button v-if="testType === TestType.E2E" class="btn btn-secondary" @click.stop="scanDevices('test')">
              <i class="fas fa-search"></i> 扫描设备
            </button>
            <div class="search-box">
              <i class="fas fa-search search-icon"></i>
              <input type="text" class="search-input" :placeholder="searchPlaceholder" v-model="resourceSearchQuery">
            </div>
            <div class="filter-select">
              <select class="form-input" v-model="resourceStatusFilter">
                <option value="all">所有状态</option>
                <option value="online">在线</option>
                <option value="offline">离线</option>
              </select>
            </div>
          </div>
        </template>

        <div v-if="voiceLlmHint" class="info-alert">
          <i class="fas fa-info-circle"></i> {{ voiceLlmHint }}
        </div>

        <ResourceSelectionGrid
          :items="resourceItems"
          :selected-ids="selectedDeviceIdsList"
          :display-fields="resourceDisplayFields"
          :empty-text="emptyResourceText"
          @toggle-selection="toggleResourceSelection"
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
        panel-id="test-step3"
        :show-actions="false"
      >
        <TestExecutionComponent
          :test-type="testTypeLabel"
          :active-tab="activeTab"
          :task-info="{
            taskName: taskName,
            expectedTotalTime: estimatedTime,
            usedTime: elapsedTime,
            expectedCompleteTime: expectedCompleteTime,
            deviceCount: testType === TestType.E2E ? associatedDevices.length : undefined,
            apiCount: testType === TestType.API ? selectedAPIIds.length : undefined,
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
        panel-id="test-step4"
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
    :mode="algorithmModalMode"
    :edit-data="(algorithmEditData as any)"
  />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { TestType } from '@/shared/types/enums'
import { useTestFlow } from '../../composables/shared/useTestFlow'
import ProgressNav from '../../components/layout/ProgressNav.vue'
import TestCaseListContainer from '../../components/common/test-case/TestCaseListContainer.vue'
import TestExecutionComponent from '../../components/layout/TestExecutionComponent.vue'
import TestStepContainer from '../../components/common/misc/TestStepContainer.vue'
import ResourceSelectionGrid from '../../components/common/data/ResourceSelectionGrid.vue'
import BasicModal from '../../components/common/modal/BasicModal.vue'
import PaginationComponent from '../../components/common/data/PaginationComponent.vue'
import AlgorithmConfigModal from '../../components/algorithm/AlgorithmConfigModal.vue'
import AlgorithmSelectionPanel from '../../components/algorithm/AlgorithmSelectionPanel.vue'
import TaskReportPanel from '../../components/report/TaskReportPanel.vue'

const props = defineProps<{
  testType: (typeof TestType)[keyof typeof TestType]
}>()

const showTaskNameModal = ref(false)
const localTaskName = ref('')

const flow = useTestFlow(props.testType)

// 解构所需状态/方法
const {
  currentStep, taskName, activeTab, concurrentTasks,
  selectedAPIIds, selectedDeviceIdsList,
  testCaseGroups, tags, tagViewData, tagViewPagination, tagViewLoading, isLoading,
  algorithmList, selectedAlgorithmType, algorithmModalVisible, algorithmModalMode,
  algorithmEditData, algorithmSearchQuery,
  apis, apiSearchQuery, apiFilter,
  associatedDevices, isExecuting, isPaused, isControlling,
  progressPercentage, completedTests, inProgressTests, pendingTests,
  executionFailedTests, evaluationFailedTests, totalTestCases,
  elapsedTime, estimatedTime, expectedCompleteTime, logs, associatedCases, apiResources,
  report, isEditingReport, isEditingConclusion, analysisContent, reportTables,
  algorithmFilteredDevices, voiceLlmHint, stepHints,
  filteredDevices, deviceSearchQuery, selectedDeviceStatus,
  currentPage, pageSize, totalItems, totalPages,
  filteredAPIs,
  goToStep, nextStep, prevStep,
  selectAlgorithm, openCreateAlgorithmModal, openAlgorithmConfigModal,
  handleDeleteGroup, handleDeleteTestCase, openAddTestCaseModal, handleOpenEditModal,
  openCreateGroupModal, openEditGroupModal, openImportTestCaseModal, openExportTestCaseModal,
  updateSelectedCases, handleTagFilterChange, handleGroupFilterChange,
  loadMoreTagView,
  toggleResourceSelection, handleResourceAction, handleAddResource,
  handlePageChange, handlePageSizeChange, handlePrevPage, handleNextPage,
  scanDevices,
  pauseTest, resumeTest, stopTest, showTestCaseDetails,
  saveReport, toggleEditReport, cancelEditReport,
  toggleEditConclusion, cancelEditConclusion, saveConclusion,
  exportResults, publishReport, startNewTest,
} = flow

// ============ 计算属性：根据 testType 派生 ============
const pageTitle = computed(() => props.testType === TestType.E2E ? '端到端测试' : 'API测试')
const pageTitleIcon = computed(() => props.testType === TestType.E2E ? 'fas fa-project-diagram' : 'fas fa-exchange-alt')
const pageDescription = computed(() => props.testType === TestType.E2E ? '通过完整的测试流程验证语音产品的功能和性能' : '测试语音服务API的功能和性能，验证接口响应和数据正确性')
const stepLabels = computed(() => props.testType === TestType.E2E
  ? ['选择算法', '选择测试用例', '选择测试设备', '执行测试', '查看结果']
  : ['选择算法', '选择测试用例', '选择被测API', '执行测试', '查看结果'])
const step2Tooltip = computed(() => props.testType === TestType.E2E ? '选择要使用的测试设备' : '选择要测试的API端点')
const step2Title = computed(() => props.testType === TestType.E2E ? '选择测试设备' : '选择被测API')
const addResourceLabel = computed(() => props.testType === TestType.E2E ? '新增设备' : '新增API')
const searchPlaceholder = computed(() => props.testType === TestType.E2E ? '搜索设备名称或型号...' : '搜索API名称或端点...')
const emptyResourceText = computed(() => props.testType === TestType.E2E ? '未找到相关设备' : '未找到相关API')
const testTypeLabel = computed(() => props.testType === TestType.E2E ? 'E2E' : 'API')

// 统一资源项
const resourceItems = computed(() => props.testType === TestType.E2E ? algorithmFilteredDevices.value : filteredAPIs.value)
// 统一搜索 query
const resourceSearchQuery = computed({
  get: () => props.testType === TestType.E2E ? deviceSearchQuery.value : apiSearchQuery.value,
  set: (val: string) => {
    if (props.testType === TestType.E2E) (deviceSearchQuery as any).value = val
    else (apiSearchQuery as any).value = val
  },
})
// 统一状态筛选
const resourceStatusFilter = computed({
  get: () => props.testType === TestType.E2E ? selectedDeviceStatus.value : apiFilter.value,
  set: (val: string) => {
    if (props.testType === TestType.E2E) (selectedDeviceStatus as any).value = val
    else (apiFilter as any).value = val
  },
})
// 资源显示字段
const resourceDisplayFields = computed(() => props.testType === TestType.E2E
  ? [
      { label: '设备名称', key: 'name' },
      { label: '型号', key: 'model' },
      { label: '序列号', key: 'serialNumber' },
      { label: '状态', key: 'status', isStatus: true },
    ]
  : [
      { key: 'apiUrl', label: '端点' },
      { key: 'description', label: '描述' },
    ])

// ============ 任务名称模态窗 ============
const handleStartTask = () => {
  const prefix = props.testType === TestType.E2E ? 'E2E测试任务' : 'API测试任务'
  localTaskName.value = `${prefix}_${new Date().toLocaleString()}`
  showTaskNameModal.value = true
}

const confirmTaskName = () => {
  showTaskNameModal.value = false
  ;(taskName as any).value = localTaskName.value
  nextStep()
}
</script>

<style>
@import '../../assets/styles/main.css';
</style>

<style scoped>
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
