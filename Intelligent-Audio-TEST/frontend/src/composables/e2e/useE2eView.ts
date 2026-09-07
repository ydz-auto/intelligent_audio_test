import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { normalizeTestCaseConfig } from '../../utils/utils'
import { useTestCaseCard } from '../testCase/useTestCaseCard'
import { useDeviceManagement } from '../device/useDeviceManagement'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import { useDeleteConfirm } from '../modal/useDeleteConfirm'
import { useE2eTest } from './useE2eTest'
import { useAlgorithmSelection } from '../algorithm/useAlgorithmSelection'
import { useTestReport } from '../shared/useTestReport'
import { normalizeSelectedCaseIds } from '../shared/useTestFlow'
import { useTestCaseStore } from '../../store/testCaseStore'
import type { TestCase, TestCaseFormData } from '../../domain'
import { TestType } from '../../domain/enums'
import { useE2eExecution } from './useE2eExecution'

export function useE2eView() {
  const router = useRouter()
  const {
    devices,
    filteredDevices,
    isLoading: devicesLoading,
    fetchDevices,
    deviceSearchQuery,
    selectedDeviceStatus,
    scanDevices,
    addDevice,
    editDevice,
    deleteDevice,
    testDeviceConnection,
    // 分页相关
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    handlePageChange,
    handlePageSizeChange,
    handlePrevPage,
    handleNextPage
  } = useDeviceManagement('test')

  const { 
    formData, 
    groupFormData, 
    editingTestCase, 
    editingGroup,
    openAddTestCaseModal,
    openEditTestCaseModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleModalSave,
    handleTestCaseAction
  } = useTestCaseCard();

  const modalManager = useModalControl()
  const { isLoading: testCasesLoading, e2eTestCaseGroups, e2eTestCases, tags, initializeE2eTests, paginationInfo, tagViewData, tagViewPagination, tagViewLoading, fetchTagView, loadMoreTagView } = useE2eTest()

  const currentStep = ref(0)
  const activeTab = ref('cases')
  const concurrentTasks = ref(4)
  const reportTables = ref([])
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const taskName = ref('')

  const {
    report,
    isEditingReport,
    isEditingConclusion,
    analysisContent,
    toggleEditReport,
    toggleEditConclusion,
    cancelEditReport,
    cancelEditConclusion,
    saveConclusion,
    exportResults,
    publishReport,
    startNewTest
  } = useTestReport()

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
    searchAlgorithms
  } = useAlgorithmSelection({
    onSelectCallback: async (type: string | null) => {
      if (type) {
        await initializeE2eTests(type)
      } else {
        await initializeE2eTests()
      }
    }
  })

  const associatedDevices = computed(() => {
    return devices.value.filter((d: any) => d.selected)
  })

  const selectedDeviceIdsList = computed(() => {
    return associatedDevices.value.map((d: any) => d.id)
  })

  const deviceDisplayFields = [
    { label: '设备名称', key: 'name' },
    { label: '型号', key: 'model' },
    { label: '序列号', key: 'serialNumber' },
    { label: '状态', key: 'status', isStatus: true }
  ]

  // 任务执行编排（Application 层）：任务创建/启动、进度订阅、暂停恢复、报告拉取
  const {
    currentTaskId,
    isExecuting,
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest,
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
    addLog,
    startTest,
    saveReport,
    stopTimeUpdateTimer
  } = useE2eExecution({
    router,
    taskName,
    concurrentTasks,
    selectedTestCaseIds,
    selectedAlgorithmType,
    e2eTestCases,
    associatedDevices,
    report,
    analysisContent,
    reportTables,
    isEditingReport,
    modalManager,
    onTaskIncomplete: () => {
      currentStep.value = 4
    }
  })

  const nextStep = async () => {
    console.log('[nextStep] 开始执行, currentStep:', currentStep.value)
    if (currentStep.value === 2) {
      const nonOnlineDevices = associatedDevices.value.filter((d: any) => d.status !== 'online')
      if (associatedDevices.value.length === 0) {
        console.log('[nextStep] 没有选择设备')
        addLog({ content: '请选择至少一个测试设备', level: 'warn' })
        return
      }
      if (nonOnlineDevices.length > 0) {
        console.log('[nextStep] 有离线设备:', nonOnlineDevices.map((d: any) => d.name))
        addLog({ content: `以下设备处于离线状态，无法执行测试：${nonOnlineDevices.map((d: any) => d.name).join(', ')}`, level: 'warn' })
        return
      }
    }

    if (currentStep.value < 4) {
      // 如果是跳转到步骤3（执行测试），需要先启动测试，成功后再切换步骤
      if (currentStep.value === 2) {
        console.log('[nextStep] 准备开始测试')
        const started = await startTest()
        console.log('[nextStep] startTest返回:', started)
        if (started) {
          console.log('[nextStep] 测试启动成功，切换到步骤3')
          currentStep.value = 3
        } else {
          console.log('[nextStep] 测试启动失败，停留在步骤2')
          // 错误信息已在startTest中显示
        }
      } else {
        // 其他步骤正常切换
        currentStep.value++
        console.log('[nextStep] currentStep增加到:', currentStep.value)
      }
    }
  }

  const prevStep = () => {
    if (currentStep.value > 0) currentStep.value--
  }

  const goToStep = (step: number) => {
    currentStep.value = step
  }

  const handleOpenEditModal = async (testCase: TestCase) => {
    editingTestCase.value = testCase
    
    const normalized = normalizeTestCaseConfig(testCase.config || {})
    const testCaseType = testCase.testType || TestType.E2E
    
    formData.value = {
      id: testCase.id,
      name: testCase.name || '',
      group: testCase.groupName || '',
      groupId: testCase.groupId || '',
      description: testCase.description || '',
      tags: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name),
      tagsInput: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name).join(', '),
      config: normalized as TestCaseFormData['config'],
      algorithmType: testCase.algorithmType || '',
      testType: testCaseType as typeof TestType[keyof typeof TestType],
      // 新设计：算法参数独立列（Domain 对象为 camelCase algorithmParams）
      algorithmParams: Array.isArray(testCase.algorithmParams) ? testCase.algorithmParams : [],
    } as TestCaseFormData
    
    try {
      const result = await modalManager.open(MODAL_TYPES.TEST_CASE_RELATED, {
        visible: true,
        mode: 'case',
        testType: testCaseType,
        formData: formData.value,
        title: '编辑测试用例',
        width: '1800px',
        maxWidth: '98vw'
      });
      
      if (result) {
        await handleModalSave(result);
      }
    } catch (error) {
      console.error('[useE2eView] 打开编辑用例模态窗失败:', error);
    }
  }

  const algorithmFilteredDevices = computed(() => {
    if (!selectedAlgorithmType.value) {
      return filteredDevices.value
    }
    return filteredDevices.value.filter(device => {
      const supportedAlgorithms = (device as any).supportedAlgorithms
      if (!supportedAlgorithms || !Array.isArray(supportedAlgorithms)) {
        return true
      }
      return supportedAlgorithms.includes(selectedAlgorithmType.value)
    })
  })

  const isVoiceLLM = computed(() => selectedAlgorithmType.value === 'voice_llm')

  const voiceLlmHint = computed(() => {
    if (!isVoiceLLM.value) return null
    return 'voice_llm 测试可能需要设备支持：音量控制、导轨控制、打断检测。请确认设备能力后再选择。'
  })

  const concurrencyHint = computed(() => {
    if (!isVoiceLLM.value) return null
    return 'voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。'
  })

  const searchDevices = () => {
  }

  const filterDevices = () => {
  }

  const handleToggleDeviceSelection = (deviceId: string | number) => {
    const device = devices.value.find((d) => String(d.id) === String(deviceId)) as
      | (Record<string, unknown> & { status?: string; selected?: boolean })
      | undefined
    if (device) {
      if (device.status !== 'online') {
        addLog({ content: '只能选择在线设备', level: 'warn' })
        return
      }
      if (device.selected === undefined) {
        device.selected = true
      } else {
        device.selected = !device.selected
      }
    }
  }

  const handleResourceAction = ({ actionId, itemId }: { actionId: string; itemId: string | number }) => {
    if (actionId === 'test') {
      testDeviceConnection(itemId, 'test')
    } else if (actionId === 'edit') {
      editDevice(itemId)
    } else if (actionId === 'delete') {
      deleteDevice(itemId)
    }
  }

  const handleSaveModal = async (data: any) => {
    try {
      const result = await handleModalSave(data);
      if (result?.needRefresh) {
        await initializeE2eTests(selectedAlgorithmType.value || undefined);
      }
    } catch (error) {
      console.error('保存失败:', error)
      const errorMessage = error instanceof Error ? error.message : '保存失败，请重试';
      addLog({ content: errorMessage, level: 'error' })
    }
  }

  const { confirmDeleteGroup, confirmDeleteTestCase } = useDeleteConfirm();

  const handleDeleteGroup = async (groupName: string) => {
    try {
      const confirmed = await confirmDeleteGroup(groupName);
      if (confirmed) {
        const store = useTestCaseStore();
        await store.deleteGroup(groupName);
        await initializeE2eTests(selectedAlgorithmType.value || undefined);
      }
    } catch (error) {
      console.error('删除分组失败:', error)
      const errorMessage = error instanceof Error ? error.message : '删除分组失败，请重试';
      addLog({ content: errorMessage, level: 'error' })
    }
  }

  const handleDeleteTestCase = async (testCase: TestCase) => {
    try {
      const confirmed = await confirmDeleteTestCase(testCase.name);
      if (confirmed) {
        const store = useTestCaseStore();
        await store.deleteTestCase(testCase.id);
        await initializeE2eTests(selectedAlgorithmType.value || undefined);
      }
    } catch (error) {
      console.error('删除测试用例失败:', error)
      const errorMessage = error instanceof Error ? error.message : '删除测试用例失败，请重试';
      addLog({ content: errorMessage, level: 'error' })
    }
  }

  const updateSelectedCases = (ids: (string | number)[]) => {
    selectedTestCaseIds.value = normalizeSelectedCaseIds(ids)
    console.log('Selected cases updated:', selectedTestCaseIds.value)
  }

  const showTestCaseDetails = (testCaseId: string | number) => {
    console.log('[showTestCaseDetails] 收到 testCaseId:', testCaseId, typeof testCaseId)
    console.log('[showTestCaseDetails] associatedCases:', associatedCases.value)
    modalManager.open(MODAL_TYPES.TEST_CASE_DETAIL, { 
      taskId: currentTaskId.value, 
      caseId: testCaseId 
    })
  }

  const skipTestCase = (id: number) => {
    console.log('Skipping test case:', id)
  }

  const removeTestCase = (id: number) => {
    console.log('Removing test case from task:', id)
  }

  const showAddTestCaseModalHandler = () => {
    openAddTestCaseModal('默认分组')
  }

  const handleAddDevice = () => {
    addDevice()
  }

  onMounted(async () => {
    await Promise.all([
      fetchDevices(),
      initializeE2eTests(),
      loadAlgorithms()
    ])
  })

  onUnmounted(() => {
    stopTimeUpdateTimer()
  })

  return {
    currentStep,
    selectedTestCaseIds,
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
    testCaseGroups: e2eTestCaseGroups,
    tags,
    tagViewData,
    tagViewPagination,
    tagViewLoading,
    isLoading: testCasesLoading,
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
    testProgress: [],
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    filteredDevices,
    algorithmFilteredDevices,
    isVoiceLLM,
    voiceLlmHint,
    concurrencyHint,
    selectedDeviceIdsList,
    deviceDisplayFields,
    analysisContent,
    reportTables,
    deviceSearchQuery,
    selectedDeviceStatus,
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
    handleSaveModal,
    updateSelectedCases,
    addDevice,
    scanDevices,
    searchDevices,
    filterDevices,
    handleToggleDeviceSelection,
    handleResourceAction,
    pauseTest,
    resumeTest,
    stopTest,
    showTestCaseDetails,
    skipTestCase,

    removeTestCase,
    showAddTestCaseModalHandler,
    handleAddDevice,
    toggleEditReport,
    saveReport,
    cancelEditReport,
    isEditingConclusion,
    toggleEditConclusion,
    cancelEditConclusion,
    saveConclusion,
    exportResults,
    publishReport,
    startNewTest,
    // 设备分页相关
    currentPage,
    pageSize,
    totalItems,
    totalPages,
    handlePageChange,
    handlePageSizeChange,
    handlePrevPage,
    handleNextPage,
    // 用例分页相关
    casePaginationInfo: paginationInfo,
    // 算法相关
    algorithmList,
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
    algorithmSearchQuery,
    searchAlgorithms,
    filteredAlgorithmList,
    fetchTagView,
    loadMoreTagView,
    initializeE2eTests
  }
}