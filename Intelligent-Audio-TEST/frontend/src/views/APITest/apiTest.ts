/**
 * apiTest —— 组合根（Composition Root）
 *
 * 原单一超大文件已按职责拆分为 apiTest.*.ts 子模块：
 * - state      页面共享响应式状态与分步常量
 * - apiList    API 列表过滤/分页展示与视图提示
 * - apiManage  API 增删改查、连通性测试与在线选择
 * - steps      分步导航、任务创建/启动执行与启停控制（含执行状态/进度计算属性）
 * - cases      用例选择、删除与弹窗编排
 * - report     任务进度维护（含完成/失败回调）、报告保存与对比数据列定义
 * - lifecycle  页面初始化（算法/用例/API 加载）
 * 本文件仅负责编排各模块与外部 composable（store、算法选择、报告编辑、弹窗等），
 * 聚合原有全部字段导出，模块路径与导出面保持不变，消费方零改动。
 */
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { deviceApiComparisonData as comparisonDeviceData, caseExecutionData as comparisonCaseData } from '../../store/reportComparisonStore'
import { useModalControl } from '../../composables/modal/useModal'
import { useDeleteConfirm } from '../../composables/modal/useDeleteConfirm'
import { useTestCaseStore } from '../../store/testCaseStore'
import { useTestCaseCard } from '../../composables/testCase/useTestCaseCard'
import { useDeviceManagement } from '../../composables/device/useDeviceManagement'
import { useAlgorithmSelection } from '../../composables/algorithm/useAlgorithmSelection'
import { useTestReport } from '../../composables/shared/useTestReport'
import { TestType } from '@/domain/enums'
import { createApiTestState } from './apiTest.state'
import { createApiListModule } from './apiTest.apiList'
import { createApiManageModule } from './apiTest.apiManage'
import { createApiTestStepsModule } from './apiTest.steps'
import { createApiTestCasesModule } from './apiTest.cases'
import { createApiTestReportModule } from './apiTest.report'
import { createApiTestLifecycleModule } from './apiTest.lifecycle'

export function useApiTest() {
  const router = useRouter()
  const testCaseStore = useTestCaseStore()
  const {
    testCaseGroups,
    tags,
    isLoading,
    paginationInfo
  } = storeToRefs(testCaseStore)

  const {
    fetchTestCases,
    deleteGroup,
    deleteTestCase
  } = testCaseStore

  const testCaseCard = useTestCaseCard();
  const {
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    openAddTestCaseModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleTestCaseAction
  } = testCaseCard

  // ===== 共享状态 =====
  const {
    currentStep,
    steps,
    apis,
    apiSearchQuery,
    apiFilter,
    selectedAPIIds,
    selectedTestCaseIds,
    activeTab,
    taskName,
    concurrentTasks,
    currentTaskId,
    apiCurrentPage,
    apiPageSize,
    apiTotalItems,
    apiTotalPages
  } = createApiTestState()

  const {
    algorithmList,
    selectedAlgorithmType,
    algorithmModalVisible,
    algorithmModalMode,
    algorithmEditData,
    algorithmSearchQuery,
  editingAlgorithm,
  filteredAlgorithmList,
  loadAlgorithms,
  selectAlgorithm,
  getAlgorithmName,
  openAlgorithmModal,
  openCreateAlgorithmModal,
  openAlgorithmConfigModal,
  closeAlgorithmModal
} = useAlgorithmSelection({
    onSelectCallback: async (type: string | null) => {
      if (type) {
        await fetchTestCases({ algorithmType: type })
      } else {
        await fetchTestCases()
      }
    }
  })

  const modalManager = useModalControl()

  // ===== 报告编辑状态（供任务进度/报告模块与导出面使用） =====
  const {
    report,
    isEditingReport,
    isEditingConclusion,
    analysisContent,
    setReport,
    toggleEditReport,
    toggleEditConclusion,
    cancelEditReport,
    cancelEditConclusion,
    saveConclusion,
    exportResults,
    publishReport,
    startNewTest
  } = useTestReport()

  // ===== 任务进度与报告保存 =====
  const {
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
    saveReport,
    deviceAPIColumns,
    caseExecutionColumns
  } = createApiTestReportModule({
    report,
    isEditingReport,
    currentTaskId,
    taskName,
    currentStep,
    router
  })

  // ===== API 列表过滤与分页 =====
  const {
    allFilteredAPIs,
    filteredAPIs,
    isVoiceLLM,
    stepHints,
    handleApiPageChange,
    handleApiPageSizeChange,
    handleApiPrevPage,
    handleApiNextPage
  } = createApiListModule({
    apis,
    apiSearchQuery,
    apiFilter,
    selectedAlgorithmType,
    apiCurrentPage,
    apiPageSize,
    apiTotalItems,
    apiTotalPages
  })

  const deviceManagement = useDeviceManagement(TestType.API)

  // ===== API 管理与选择 =====
  const {
    openAPIEditModal,
    searchAPIs,
    filterAPIs,
    deleteAPI,
    testAPI,
    healthCheck,
    showAPIDetails,
    editAPI,
    toggleAPISelection
  } = createApiManageModule({
    apis,
    apiSearchQuery,
    apiFilter,
    selectedAPIIds,
    modalManager,
    deviceManagement
  })

  // ===== 分步导航与任务执行 =====
  const {
    nextStep,
    prevStep,
    goToStep,
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest,
    isExecuting,
    executionProgress
  } = createApiTestStepsModule({
    currentStep,
    selectedTestCaseIds,
    selectedAPIIds,
    apis,
    taskName,
    concurrentTasks,
    currentTaskId,
    testCaseGroups,
    selectedAlgorithmType,
    testCaseStore,
    associatedCases,
    totalTestCases,
    pendingTests,
    estimatedTime,
    expectedCompleteTime,
    taskStatus,
    progressPercentage
  })

  const deleteConfirm = useDeleteConfirm();

  // ===== 用例管理与弹窗编排 =====
  const {
    updateSelectedCases,
    handleDeleteGroup,
    handleDeleteTestCase,
    handleOpenEditModal,
    handleSaveModal,
    showTestCaseDetails,
    skipTestCase,
    showAddTestCaseModalHandler,
    removeTestCase
  } = createApiTestCasesModule({
    selectedTestCaseIds,
    currentTaskId,
    modalManager,
    testCaseCard,
    deleteConfirm,
    testCaseStore,
    selectedAlgorithmType
  })

  // 对比数据 ReadModel（来自报告对比 store 单例 ref，直接别名暴露）
  const deviceApiComparisonData = comparisonDeviceData
  const caseExecutionData = comparisonCaseData

  // ===== 初始化与生命周期 =====
  const {
    initAPITest
  } = createApiTestLifecycleModule({
    apis,
    selectedAlgorithmType,
    loadAlgorithms,
    fetchTestCases
  })

  return {
    currentStep,
    steps,
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
    filteredAPIs,
    allFilteredAPIs,
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
    testCaseGroups,
    tags,
    isLoading,
    casePaginationInfo: paginationInfo,
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
    openAPIEditModal,
    deleteAPI,
    testAPI,
    healthCheck,
    showAPIDetails,
    editAPI,
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
    isEditingConclusion,
    toggleEditConclusion,
    cancelEditConclusion,
    saveConclusion,
    exportResults,
    skipTestCase,
    removeTestCase,
    startNewTest,
    deviceAPIColumns,
    caseExecutionColumns,
    algorithmList,
    filteredAlgorithmList,
    algorithmSearchQuery,
    selectedAlgorithmType,
    loadAlgorithms,
    selectAlgorithm,
    getAlgorithmName,
    openAlgorithmModal,
    openCreateAlgorithmModal,
    openAlgorithmConfigModal,
    closeAlgorithmModal,
    algorithmModalVisible,
    algorithmModalMode,
    algorithmEditData,
    editingAlgorithm,
    isVoiceLLM,
    stepHints
  }
}
