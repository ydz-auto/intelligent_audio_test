<template>
  <div class="test-view-common">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary);">
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
          :algorithm-type-filter="selectedAlgorithmType || ViewMode.ALL"
          :test-type-filter="testType"
          :is-loading="isLoading || false"
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

      <!-- 步骤2：选择资源（设备/API 混选 + 执行参数） -->
      <TestStepContainer
        :is-active="currentStep === 2"
        panel-id="test-step2"
        :title="step2Title"
        next-label="开始任务"
        @prev="prevStep"
        @next="handleStartTask"
      >
        <div v-if="voiceLlmHint" class="info-alert">
          <i class="fas fa-info-circle"></i> {{ voiceLlmHint }}
        </div>

        <!-- 设备区 -->
        <div class="resource-section">
          <div class="resource-section-header">
            <h4><i class="fas fa-mobile-alt"></i> 测试设备</h4>
          </div>
          <div class="device-toolbar">
            <button class="btn btn-primary" @click="() => addDevice()">
              <i class="fas fa-plus"></i> 新增设备
            </button>
            <button class="btn btn-secondary" @click.stop="() => scanDevices('test')">
              <i class="fas fa-search"></i> 扫描设备
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

          <ResourceSelectionGrid
            :items="algorithmFilteredDevices"
            :selected-ids="selectedDeviceIdsList"
            :display-fields="deviceDisplayFields"
            :empty-text="emptyDeviceText"
            @toggle-selection="handleToggleDeviceSelection"
            @action-click="handleDeviceResourceAction"
          />

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
        </div>

        <!-- 被测 API 区 -->
        <div class="resource-section">
          <div class="resource-section-header">
            <h4><i class="fas fa-server"></i> 被测 API</h4>
          </div>
          <div class="device-toolbar">
            <button class="btn btn-primary" @click="() => openAPIEditModal()">
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

          <ResourceSelectionGrid
            :items="filteredAPIs"
            :selected-ids="selectedAPIIds"
            :display-fields="apiDisplayFields"
            :empty-text="emptyApiText"
            @toggle-selection="toggleAPISelection"
            @action-click="handleApiResourceAction"
          />

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

        <!-- 执行参数区（INT-604：执行模式 并行/串行 + 串行优先侧） -->
        <div class="execution-params-panel">
          <div class="params-title"><i class="fas fa-cog"></i> 执行参数</div>
          <div class="params-body">
            <div class="param-group" :class="{ disabled: !isMixedSelection }" :title="executionModeDisabledTip">
              <span class="param-label">执行模式</span>
              <div class="radio-group">
                <label class="radio-label">
                  <input type="radio" :value="'parallel'" v-model="executionMode" :disabled="!isMixedSelection" />
                  <span>并行</span>
                </label>
                <label class="radio-label">
                  <input type="radio" :value="'serial'" v-model="executionMode" :disabled="!isMixedSelection" />
                  <span>串行</span>
                </label>
              </div>
            </div>
            <div class="param-group" v-if="executionMode === 'serial'" :class="{ disabled: !isMixedSelection }" :title="executionModeDisabledTip">
              <span class="param-label">串行优先侧</span>
              <div class="radio-group">
                <label class="radio-label">
                  <input type="radio" :value="'device'" v-model="serialFirst" :disabled="!isMixedSelection" />
                  <span>设备先</span>
                </label>
                <label class="radio-label">
                  <input type="radio" :value="'api'" v-model="serialFirst" :disabled="!isMixedSelection" />
                  <span>API先</span>
                </label>
              </div>
            </div>
            <div v-if="!isMixedSelection" class="param-hint">
              <i class="fas fa-info-circle"></i> 仅同时选择设备与 API 时可用
            </div>
          </div>
        </div>
      </TestStepContainer>

      <!-- 步骤3：执行测试 -->
      <TestStepContainer
        :is-active="currentStep === 3"
        panel-id="test-step3"
        :show-actions="false"
      >
        <!-- INT-1072 返工 P1：关联设备/API 页签数据源并入混选两侧——TestExecutionComponent 该页签按
             associatedDevices 渲染（与 TaskDetailModal 的 devices+apis 合并口径一致），
             API 模式纯选 API 时亦须展示所选 API（旧语义 associatedDevices=所选资源） -->
        <TestExecutionComponent
          :test-type="testTypeLabel"
          :active-tab="activeTab"
          :task-status="taskStatus"
          :execution-status="taskExecutionStatus"
          :evaluation-status="taskEvaluationStatus"
          :task-info="{
            taskName: taskName,
            expectedTotalTime: estimatedTime,
            usedTime: elapsedTime,
            expectedCompleteTime: expectedCompleteTime,
            deviceCount: associatedDevices.length || undefined,
            apiCount: selectedAPIIds.length || undefined,
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
          :associated-devices="[...associatedDevices, ...associatedAPIs]"
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
      <!-- INT-423/467：新建任务可见性选择器（默认共享；切换记录 localStorage 偏好） -->
      <div class="form-group">
        <label>可见性</label>
        <VisibilitySelector :model-value="taskVisibility" @change="handleVisibilityChange" />
      </div>
    </div>
  </BasicModal>

  <!-- 算法配置模态窗 -->
  <AlgorithmConfigModal
    v-model:visible="algorithmModalVisible"
    :mode="algorithmModalMode"
    :edit-data="algorithmEditDataForModal"
  />
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { ref, computed } from 'vue'
import { TestType, ViewMode, DeviceStatus, ApiEndpointStatus } from '@/domain/enums'
import type { AlgorithmDefinition } from '@/domain'
import { useTestFlow } from '../../composables/shared/useTestFlow'
import ProgressNav from '../../components/layout/ProgressNav.vue'
import TestCaseListContainer from '../../components/common/test-case/TestCaseListContainer.vue'
import TestExecutionComponent from '../../components/layout/TestExecutionComponent.vue'
import TestStepContainer from '../../components/common/misc/TestStepContainer.vue'
import ResourceSelectionGrid from '../../components/common/data/ResourceSelectionGrid.vue'
import BasicModal from '../../components/common/modal/BasicModal.vue'
import VisibilitySelector from '../../components/common/visibility/VisibilitySelector.vue'
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
  taskVisibility, handleVisibilityChange,
  executionMode, serialFirst, isMixedSelection,
  selectedAPIIds, selectedDeviceIdsList,
  testCaseGroups, tags, tagViewData, tagViewPagination, tagViewLoading, isLoading,
  algorithmList, selectedAlgorithmType, algorithmModalVisible, algorithmModalMode,
  algorithmEditData, algorithmSearchQuery,
  apis, apiSearchQuery, apiFilter,
  associatedDevices, associatedAPIs, isExecuting, isPaused, isControlling,
  progressPercentage, completedTests, inProgressTests, pendingTests,
  executionFailedTests, evaluationFailedTests, totalTestCases,
  taskStatus, taskExecutionStatus, taskEvaluationStatus,
  elapsedTime, estimatedTime, expectedCompleteTime, logs, associatedCases, apiResources,
  isProgressPolling,
  report, isEditingReport, isEditingConclusion, analysisContent, reportTables,
  algorithmFilteredDevices, voiceLlmHint, stepHints,
  filteredDevices, deviceSearchQuery, selectedDeviceStatus,
  currentPage, pageSize, totalItems, totalPages,
  filteredAPIs, apiCurrentPage, apiPageSize, apiTotalItems, apiTotalPages,
  handleApiPageChange, handleApiPageSizeChange, handleApiPrevPage, handleApiNextPage,
  deviceDisplayFields, apiDisplayFields,
  goToStep, nextStep, prevStep,
  selectAlgorithm, openCreateAlgorithmModal, openAlgorithmConfigModal,
  handleDeleteGroup, handleDeleteTestCase, handleOpenAddModal, handleOpenEditModal,
  openCreateGroupModal, openEditGroupModal, openImportTestCaseModal, openExportTestCaseModal,
  updateSelectedCases, handleTagFilterChange, handleGroupFilterChange,
  loadMoreTagView,
  handleToggleDeviceSelection, toggleAPISelection,
  handleDeviceResourceAction, handleApiResourceAction,
  handleResourceAction, handleAddResource, openAPIEditModal,
  handlePageChange, handlePageSizeChange, handlePrevPage, handleNextPage,
  scanDevices, addDevice,
  pauseTest, resumeTest, stopTest, showTestCaseDetails,
  saveReport, toggleEditReport, cancelEditReport,
  toggleEditConclusion, cancelEditConclusion, saveConclusion,
  exportResults, publishReport, startNewTest,
} = flow

// INT-293：算法编辑数据断言收敛——模板不再写 (algorithmEditData as any)，
// 在 view 层以 AlgorithmConfigModal 期望的具体目标类型做一次边界转换
const algorithmEditDataForModal = computed<AlgorithmDefinition | null>(() =>
  algorithmEditData.value ? (algorithmEditData.value as unknown as AlgorithmDefinition) : null
)

// ============ 计算属性：根据 testType 派生 ============
const pageTitle = computed(() => props.testType === TestType.E2E ? '端到端测试' : 'API测试')
const pageTitleIcon = computed(() => props.testType === TestType.E2E ? 'fas fa-project-diagram' : 'fas fa-exchange-alt')
const pageDescription = computed(() => props.testType === TestType.E2E ? '通过完整的测试流程验证语音产品的功能和性能' : '测试语音服务API的功能和性能，验证接口响应和数据正确性')
// INT-604/INT-1072：混选前置——步骤二同屏选择设备与 API（不再按模式二选一）
const stepLabels = computed(() => ['选择算法', '选择测试用例', '选择设备/API', '执行测试', '查看结果'])
const step2Tooltip = computed(() => '选择测试设备与被测API，同一任务可混选')
const step2Title = computed(() => '选择设备/API 与执行参数')
const testTypeLabel = computed(() => props.testType === TestType.E2E ? 'E2E' : 'API')
const emptyDeviceText = '未找到相关设备'
const emptyApiText = '未找到相关API'
// INT-604：未混选时执行模式控件置灰提示
const executionModeDisabledTip = '仅同时选择设备与 API 时可用'

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

<style scoped>

.device-toolbar{
margin-bottom: 20px;
padding: 16px;
background: linear-gradient(135deg, var(--color-white) 0%, var(--muted) 100%);
border-radius: var(--radius-lg);
box-shadow: var(--shadow-sm);
border: 1px solid var(--gray-light);
}

/* INT-604/INT-1072：混选分区 + 执行参数区 */
.resource-section{
  margin-bottom: 24px;
}
.resource-section-header{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.resource-section-header h4{
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--primary);
}
.execution-params-panel{
  margin-top: 8px;
  padding: 16px;
  background: linear-gradient(135deg, var(--color-white) 0%, var(--muted) 100%);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--gray-light);
}
.params-title{
  font-size: 15px;
  font-weight: 600;
  color: var(--primary);
  margin-bottom: 12px;
}
.params-body{
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
}
.param-group{
  display: flex;
  align-items: center;
  gap: 12px;
}
.param-group.disabled{
  opacity: 0.5;
}
.param-group.disabled .radio-label{
  cursor: not-allowed;
}
.param-label{
  font-size: 14px;
  font-weight: 500;
  color: var(--muted-foreground);
  min-width: 64px;
}
.param-hint{
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  font-size: 13px;
  color: var(--muted-foreground);
}
.radio-group{
  display: flex;
  gap: 16px;
}
.radio-label{
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--foreground);
  cursor: pointer;
}
.radio-label input[type="radio"]{
  width: 16px;
  height: 16px;
  accent-color: var(--primary);
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















/* step-content - 自全局样式就近迁移 */
.step-content{
background-color: var(--color-white);
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
</style>

<!-- INT-768 CSS-1 拆搬：api-test 域样式由本页（APITest/E2ETest/TestFlow 共用）按需加载 -->
<style src="../../assets/styles/api-test/api-test.css"></style>
