import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'
import { useAlgorithmSelection } from '../algorithm/useAlgorithmSelection'
import { useTaskProgress } from '../task/useTaskProgress'
import { useTestControl } from './useTestControl'
import { useTestSteps } from './useTestSteps'
import { useTestTimer } from './useTestTimer'
import { useTestReportOps } from './useTestReportOps'
import { useTestCaseOps } from './useTestCaseOps'
import { useResourceSelection } from './useResourceSelection'
import { useTaskExecution } from './useTaskExecution'
import { useTestCaseStore } from '../../store/testCaseStore'

export function normalizeSelectedCaseIds(ids: (string | number)[]) {
  const normalizedIds = ids.filter((id): id is string | number => {
    if (id === null || id === undefined) return false
    if (typeof id === 'number') return Number.isFinite(id)
    return String(id).trim().length > 0
  })
  const seen = new Set<string>()
  const uniqueIds: (string | number)[] = []
  for (const id of normalizedIds) {
    const key = String(id)
    if (seen.has(key)) continue
    seen.add(key)
    uniqueIds.push(id)
  }
  return uniqueIds
}

/**
 * 测试流程编排层：组合各小 composable，对外暴露统一的 API
 * 仅做组合，不包含具体业务逻辑
 */
export function useTestFlow(testType: 'e2e' | 'api') {
  // ============ 基础状态 ============
  const taskName = ref(testType === 'e2e' ? '' : 'API测试任务')
  const activeTab = ref('cases')
  const concurrentTasks = ref(testType === 'e2e' ? 4 : 5)
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const currentTaskId = ref<number | string | null>(null)

  // ============ 步骤导航 ============
  const { currentStep, goToStep } = useTestSteps(4)

  // ============ 算法选择 ============
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
    closeAlgorithmModal,
    searchAlgorithms,
  } = useAlgorithmSelection({
    onSelectCallback: async (type: string | null) => {
      const testCaseStore = useTestCaseStore()
      if (type) {
        await testCaseStore.fetchTestCases({ algorithmType: type })
      } else {
        await testCaseStore.fetchTestCases()
      }
    },
  })

  // ============ 任务进度（需要 addLog 给后续 composable 用，先占位） ============
  let addLogRef: (log: any) => void = () => {}

  // ============ 报告操作 ============
  const {
    report, isEditingReport, isEditingConclusion, analysisContent, reportTables,
    deviceApiComparisonData, caseExecutionData, deviceApiColumns, caseExecutionColumns,
    setReport, toggleEditReport, toggleEditConclusion, cancelEditReport, cancelEditConclusion,
    saveConclusion, exportResults, publishReport, startNewTest,
    fetchReport, handleTaskEnd, saveReport,
  } = useTestReportOps({
    testType,
    currentTaskId,
    taskName,
    onReportReady: () => {},
    onReportFailed: () => { currentStep.value = 4 },
  })

  // ============ 任务进度（先声明占位回调，真正注册在后面完成依赖收集后） ============
  // 为了避免 TDZ，我们先创建 timer / execution，再注册 progress 回调
  // 但 useTaskProgress 内部 onMounted 才注册 socket，所以可以先拿到其返回的 ref
  // 这里采用「先声明空回调对象，后赋值」的模式
  let progressCallbacks: { onCompleted?: () => Promise<void>; onFailed?: () => Promise<void> } = {}

  const {
    progressPercentage, completedTests, inProgressTests, pendingTests,
    executionFailedTests, evaluationFailedTests, totalTestCases, taskStatus,
    elapsedTime, estimatedTime, expectedCompleteTime, logs, associatedCases,
    apiResources, resetProgress, addLog,
  } = useTaskProgress({
    testType: testType === 'e2e' ? 'E2E' : 'API',
    currentTaskId: currentTaskId as any,
    onCompleted: async () => { await progressCallbacks.onCompleted?.() },
    onFailed: async () => { await progressCallbacks.onFailed?.() },
  })

  addLogRef = addLog

  // ============ E2E 计时器（仅 e2e 使用，需在 useTaskProgress 之后拿 elapsedTime） ============
  const {
    taskStartTime, taskElapsedTimeDisplay,
    startTimeUpdateTimer, stopTimeUpdateTimer, setStartTime,
  } = useTestTimer(elapsedTime)

  // ============ 测试用例操作 ============
  const {
    formData, groupFormData, editingTestCase, editingGroup,
    testCaseGroups, tags, tagViewData, isLoading, casePaginationInfo,
    e2eTestCases,
    initializeTestCases, fetchTagView, handleTagFilterChange,
    handleDeleteGroup, handleDeleteTestCase, handleSaveModal,
    handleOpenEditModal, showTestCaseDetails: _showTestCaseDetails,
    openAddTestCaseModal, openCreateGroupModal, openEditGroupModal,
    openImportTestCaseModal, openExportTestCaseModal,
  } = useTestCaseOps({
    testType,
    selectedAlgorithmType,
    addLog,
  })

  // ============ 资源选择（设备/API） ============
  const {
    deviceManagement, apis, apiSearchQuery, apiFilter, selectedAPIIds,
    filteredAPIs, allFilteredAPIs,
    apiCurrentPage, apiPageSize, apiTotalItems, apiTotalPages,
    handleApiPageChange, handleApiPageSizeChange, handleApiPrevPage, handleApiNextPage,
    associatedResources, selectedResourceIds, algorithmFilteredDevices,
    toggleResourceSelection, handleToggleDeviceSelection, toggleAPISelection,
    handleResourceAction, handleAddResource, openAPIEditModal, deleteAPI, testAPI, editAPI, loadAPIs,
    deviceSearchQuery, selectedDeviceStatus,
    currentPage, pageSize, totalItems, totalPages,
    handlePageChange, handlePageSizeChange, handlePrevPage, handleNextPage,
    filteredDevices, scanDevices, addDevice,
  } = useResourceSelection({
    testType,
    selectedAlgorithmType,
    addLog,
  })

  // ============ 任务执行（依赖以上 composable 的 ref） ============
  const {
    e2eIsExecuting, canStartTest, startE2eTest, startApiTask, startTask,
  } = useTaskExecution({
    testType,
    currentTaskId,
    taskName,
    concurrentTasks,
    selectedTestCaseIds,
    selectedDeviceIds: selectedResourceIds as any,
    e2eTestCases,
    selectedAPIIds,
    apis,
    testCaseGroups,
    resetProgress,
    associatedCases,
    totalTestCases,
    pendingTests,
    estimatedTime,
    expectedCompleteTime,
    addLog,
    onE2eStart: (startResponse: any) => {
      setStartTime(startResponse.startTime)
      startTimeUpdateTimer()
    },
  })

  // ============ 延迟赋值 progress 回调（此时 e2eIsExecuting / stopTimeUpdateTimer 已定义） ============
  progressCallbacks = {
    onCompleted: async () => {
      if (testType === 'e2e') {
        e2eIsExecuting.value = false
        stopTimeUpdateTimer()
      }
      await handleTaskEnd('completed', 100)
    },
    onFailed: async () => {
      if (testType === 'e2e') {
        e2eIsExecuting.value = false
        stopTimeUpdateTimer()
      }
      await handleTaskEnd('failed', progressPercentage.value)
    },
  }

  // ============ 测试控制（暂停/恢复/停止） ============
  const {
    isPaused, isControlling, pauseTest, resumeTest, stopTest,
  } = useTestControl({
    currentTaskId: currentTaskId as any,
    onStopped: () => {
      if (testType === 'e2e') {
        e2eIsExecuting.value = false
        stopTimeUpdateTimer()
      }
    },
    ...(testType === 'e2e' ? { addLog: (log: any) => addLogRef(log) } : {}),
  })

  // ============ isExecuting 统一 ============
  const isExecuting = computed(() => {
    if (testType === 'e2e') return e2eIsExecuting.value
    return taskStatus.value === 'running' || taskStatus.value === 'starting' || taskStatus.value === 'pending'
  })

  const executionProgress = computed(() => progressPercentage.value)

  // ============ voice_llm 提示 ============
  const isVoiceLLM = computed(() => selectedAlgorithmType.value === 'voice_llm')
  const voiceLlmHint = computed(() => {
    if (testType !== 'e2e' || !isVoiceLLM.value) return null
    return 'voice_llm 测试可能需要设备支持：音量控制、导轨控制、打断检测。请确认设备能力后再选择。'
  })
  const concurrencyHint = computed(() => {
    if (testType !== 'e2e' || !isVoiceLLM.value) return null
    return 'voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。'
  })
  const stepHints = computed(() => {
    if (testType !== 'api' || !isVoiceLLM.value) return {} as Record<string, string>
    return { caseSelection: 'voice_llm 用例支持多轮对话，每个用例可配置多个轮次的输入文本/音频' }
  })

  // ============ 显示用例详情 ============
  const showTestCaseDetails = (testCaseId: string | number) => {
    _showTestCaseDetails(testCaseId, currentTaskId.value)
  }

  // ============ 更新选中用例 ============
  const updateSelectedCases = (ids: (string | number)[]) => {
    if (testType === 'e2e') {
      selectedTestCaseIds.value = normalizeSelectedCaseIds(ids)
    } else {
      selectedTestCaseIds.value = ids
    }
  }

  // ============ 资源显示字段 ============
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

  // ============ nextStep / prevStep ============
  const nextStep = async () => {
    if (testType === 'e2e') {
      if (currentStep.value === 2) {
        const nonOnlineDevices = associatedResources.value.filter((d: any) => d.status !== 'online')
        if (associatedResources.value.length === 0) {
          addLog({ content: '请选择至少一个测试设备', level: 'warn' })
          return
        }
        if (nonOnlineDevices.length > 0) {
          addLog({ content: `以下设备处于离线状态，无法执行测试：${nonOnlineDevices.map((d: any) => d.name).join(', ')}`, level: 'warn' })
          return
        }
      }
      if (currentStep.value < 4) {
        if (currentStep.value === 2) {
          const started = await startE2eTest()
          if (started) currentStep.value = 3
        } else {
          currentStep.value++
        }
      }
    } else {
      if (currentStep.value === 2) {
        const started = await startApiTask()
        if (!started) return
      }
      if (currentStep.value < 4) currentStep.value++
    }
  }

  const prevStep = () => {
    if (testType === 'e2e') {
      if (currentStep.value > 0) currentStep.value--
    } else {
      if (currentStep.value > 1) currentStep.value--
    }
  }

  // ============ 步骤定义 ============
  const steps = [
    { number: 0, title: '选择算法', description: '选择测试所使用的算法' },
    { number: 1, title: '选择用例', description: '选择需要执行的测试用例' },
    { number: 2, title: testType === 'e2e' ? '选择测试设备' : '配置参数', description: testType === 'e2e' ? '选择测试设备' : '配置执行参数和设备' },
    { number: 3, title: '执行测试', description: '运行测试并监控进度' },
    { number: 4, title: '查看报告', description: '查看和导出测试报告' },
  ]

  // ============ 初始化 ============
  const initTest = async () => {
    await loadAlgorithms()
    const algorithmType = selectedAlgorithmType.value || undefined
    await initializeTestCases(algorithmType)
    if (testType === 'api') {
      await loadAPIs()
    }
  }

  onMounted(async () => {
    if (testType === 'e2e') {
      await Promise.all([initializeTestCases(), loadAlgorithms()])
    } else {
      await initTest()
    }
  })

  onUnmounted(() => {
    if (testType === 'e2e') stopTimeUpdateTimer()
  })

  return {
    testType,
    currentStep, steps, selectedTestCaseIds, taskName, activeTab, concurrentTasks,
    currentTaskId, taskStartTime, taskElapsedTimeDisplay,
    testCaseGroups, tags, tagViewData, isLoading, casePaginationInfo,
    fetchTagView, handleTagFilterChange,
    associatedDevices: associatedResources, selectedDeviceIdsList: selectedResourceIds,
    apis, apiSearchQuery, apiFilter, selectedAPIIds, filteredAPIs, allFilteredAPIs,
    apiCurrentPage, apiPageSize, apiTotalItems, apiTotalPages,
    handleApiPageChange, handleApiPageSizeChange, handleApiPrevPage, handleApiNextPage,
    toggleResourceSelection, handleToggleDeviceSelection, toggleAPISelection,
    handleResourceAction, handleAddResource, openAPIEditModal, deleteAPI, testAPI, editAPI,
    deviceDisplayFields, apiDisplayFields,
    isExecuting, executionProgress, isPaused, isControlling, pauseTest, resumeTest, stopTest,
    progressPercentage, completedTests, inProgressTests, pendingTests,
    executionFailedTests, evaluationFailedTests, totalTestCases, taskStatus,
    elapsedTime, estimatedTime, expectedCompleteTime, logs, associatedCases,
    apiResources, testProgress: [] as any[],
    report, isEditingReport, isEditingConclusion, analysisContent, reportTables,
    deviceApiComparisonData, caseExecutionData, deviceApiColumns, caseExecutionColumns,
    toggleEditReport, saveReport, cancelEditReport, toggleEditConclusion,
    cancelEditConclusion, saveConclusion, exportResults, publishReport, startNewTest,
    formData, groupFormData, editingTestCase, editingGroup,
    algorithmList, selectedAlgorithmType, algorithmModalVisible, algorithmModalMode,
    algorithmEditData, algorithmSearchQuery, editingAlgorithm, filteredAlgorithmList,
    loadAlgorithms, selectAlgorithm, getAlgorithmName, openAlgorithmModal,
    openCreateAlgorithmModal, openAlgorithmConfigModal, closeAlgorithmModal, searchAlgorithms,
    algorithmFilteredDevices, isVoiceLLM, voiceLlmHint, concurrencyHint, stepHints, canStartTest,
    goToStep, nextStep, prevStep,
    handleDeleteGroup, handleDeleteTestCase, openAddTestCaseModal, handleOpenEditModal,
    openCreateGroupModal, openEditGroupModal, openImportTestCaseModal, openExportTestCaseModal,
    handleSaveModal, updateSelectedCases, showTestCaseDetails,
    deviceSearchQuery, selectedDeviceStatus,
    currentPage, pageSize, totalItems, totalPages,
    handlePageChange, handlePageSizeChange, handlePrevPage, handleNextPage,
    filteredDevices, scanDevices, addDevice,
    initTest,
  }
}
