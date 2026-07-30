import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { tasksApi, reportsApi, testcasesApi, groupsApi } from '../utils/api'
import { normalizeTestCaseConfig } from '../utils/utils'
import { useTestCaseCard } from './useTestCaseCard'
import { useDeviceManagement } from './useDeviceManagement'
import { useTaskProgress } from './useTaskProgress'
import { useModalControl, MODAL_TYPES } from './useModal'
import { useDeleteConfirm } from './useDeleteConfirm'
import { useE2eTest } from './useE2eTest'
import { useTestControl } from './useTestControl'
import { useAlgorithmSelection } from './useAlgorithmSelection'
import { useTestReport } from './useTestReport'
import { useTestCaseStore } from '../store/testCaseStore'
import { type Report, type Log, type TestCase, type TestCaseFormData } from '../shared/types'
import reportService from '../services/reportService'

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
  const { isLoading: testCasesLoading, e2eTestCaseGroups, e2eTestCases, tags, initializeE2eTests, paginationInfo, tagViewData, fetchTagView } = useE2eTest()

  const currentStep = ref(0)
  const currentTaskId = ref<number | null>(null)
  const isExecuting = ref(false)
  const activeTab = ref('cases')
  const concurrentTasks = ref(4)
  const reportTables = ref([])
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const taskName = ref('')
  const taskStartTime = ref<Date | null>(null)
  const taskElapsedTimeDisplay = ref('00:00:00')
  let timeUpdateTimer: ReturnType<typeof setInterval> | null = null

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

  const {
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest
  } = useTestControl({
    currentTaskId: currentTaskId as any,
    onStopped: () => {
      isExecuting.value = false
      stopTimeUpdateTimer()
    },
    addLog: (log) => addLog(log)
  })

  const stopTimeUpdateTimer = () => {
    if (timeUpdateTimer) {
      clearInterval(timeUpdateTimer)
      timeUpdateTimer = null
    }
  }

  const startTimeUpdateTimer = () => {
    stopTimeUpdateTimer()
    timeUpdateTimer = setInterval(() => {
      if (!taskStartTime.value) return
      const now = new Date()
      const elapsedSeconds = Math.floor((now.getTime() - taskStartTime.value.getTime()) / 1000)
      const hoursStr = String(Math.floor(elapsedSeconds / 3600)).padStart(2, '0')
      const minutesStr = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, '0')
      const secondsStr = String(elapsedSeconds % 60).padStart(2, '0')
      taskElapsedTimeDisplay.value = `${hoursStr}:${minutesStr}:${secondsStr}`
      // 同步更新 elapsedTime，让组件显示已用时长
      if (elapsedSeconds < 60) {
        elapsedTime.value = `${elapsedSeconds}秒`
      } else if (elapsedSeconds < 3600) {
        const m = Math.floor(elapsedSeconds / 60)
        const s = elapsedSeconds % 60
        elapsedTime.value = s > 0 ? `${m}分钟${s}秒` : `${m}分钟`
      } else {
        const h = Math.floor(elapsedSeconds / 3600)
        const m = Math.floor((elapsedSeconds % 3600) / 60)
        elapsedTime.value = m > 0 ? `${h}小时${m}分钟` : `${h}小时`
      }
    }, 1000)
  }

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
    resetProgress,
    addLog
  } = useTaskProgress({
    testType: 'E2E',
    currentTaskId,
    onCompleted: async (data: any) => {
      isExecuting.value = false
      stopTimeUpdateTimer()
      await fetchReport()
      if (report.value?.id) {
        router.push({ name: 'reportView', params: { id: report.value.id } })
      } else {
        currentStep.value = 4
      }
    },
    onFailed: (data: any) => {
      isExecuting.value = false
      stopTimeUpdateTimer()
      fetchReport()
      if (report.value?.id) {
        router.push({ name: 'reportView', params: { id: report.value.id } })
      } else {
        currentStep.value = 4
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

  const canStartTest = computed(() => {
    return associatedDevices.value.length > 0 && !isExecuting.value
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

  const fetchReport = async () => {
    if (!currentTaskId.value) return
    try {
      // 使用 reportService.viewTaskReport 统一处理异步报告生成（监听 socket report_generated 事件）
      const reportData = await reportService.viewTaskReport({
        id: currentTaskId.value,
        name: taskName.value || 'E2E测试任务',
        type: 'e2e',
        status: 'completed',
        progress: 100,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      } as any)
      if (reportData) {
        report.value = { ...report.value, ...reportData } as any
        analysisContent.value = (report.value as any)?.analysis || ''
        reportTables.value = (report.value as any)?.tables || []
      }
    } catch (error) {
      console.error('获取报告失败:', error)
      const errorMessage = error instanceof Error ? error.message : '生成报告失败，请检查任务状态'
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '报告生成失败',
        content: errorMessage,
        confirmText: '确定',
        cancelText: '关闭',
        danger: true
      })
    }
  }

  const startTest = async () => {
    console.log('[startTest] 开始执行, canStartTest:', canStartTest.value)
    if (!canStartTest.value) {
      console.log('[startTest] 无法开始测试，canStartTest为false')
      return false
    }

    try {
      if (associatedDevices.value.length === 0) {
        console.log('[startTest] 没有选择设备')
        throw new Error('请选择至少一个测试设备')
      }

      const selectedCaseIds = selectedTestCaseIds.value.length > 0 ? selectedTestCaseIds.value : e2eTestCases.value.map((c: any) => c.id)
      console.log('[startTest] selectedCaseIds数量:', selectedCaseIds.length, 'selectedTestCaseIds:', selectedTestCaseIds.value.length, 'e2eTestCases:', e2eTestCases.value.length)
      if (selectedCaseIds.length === 0) {
        console.log('[startTest] 没有可用的E2E测试用例')
        throw new Error('没有可用的E2E测试用例')
      }

      const nonOnlineDevices = associatedDevices.value.filter((d: any) => d.status !== 'online')
      if (nonOnlineDevices.length > 0) {
        console.log('[startTest] 有离线设备:', nonOnlineDevices.map((d: any) => d.name))
        throw new Error(`以下设备处于离线状态，无法执行测试：${nonOnlineDevices.map((d: any) => d.name).join(', ')}`)
      }

      isExecuting.value = true
      isPaused.value = false
      resetProgress()
      // currentStep.value = 3  // 不在这里设置，由nextStep控制
      console.log('[startTest] 准备创建任务')

      const selectedDeviceIds = associatedDevices.value.map((d: any) => d.id)
      console.log('[startTest] 选择的设备数量:', selectedDeviceIds.length)

      const payload = {
        name: taskName.value || `E2E测试任务_${new Date().toLocaleString()}`,
        type: 'e2e',
        deviceIds: selectedDeviceIds,
        caseIds: selectedCaseIds,
        config: { parallel: true, concurrentTasks: concurrentTasks.value }
      }

      addLog({ content: '正在创建测试任务...', level: 'info' })
      console.log('[startTest] 发起创建任务API请求')
      const response = await tasksApi.create(payload)
      console.log('[startTest] 任务创建响应:', response)
      currentTaskId.value = response.id

      console.log('[E2E测试] selectedTestCaseIds:', selectedTestCaseIds.value)
      console.log('[E2E测试] e2eTestCases数量:', e2eTestCases.value.length)
      
      associatedCases.value = selectedCaseIds.map((id: any) => ({
        id: id,
        name: e2eTestCases.value.find((c: any) => String(c.id) === String(id))?.name || `用例 ${id}`,
        status: 'pending',
        executionStatus: 'pending',
        evaluationStatus: 'pending'
      }))
      
      console.log('[E2E测试] associatedCases:', associatedCases.value)
      totalTestCases.value = associatedCases.value.length
      pendingTests.value = totalTestCases.value

      addLog({ content: '测试任务已创建，正在启动...', level: 'info' })
      const startResponse = await tasksApi.start(response.id)
      console.log('[startTest] 启动任务响应:', startResponse)

      // 设置任务开始时间并启动本地已用时长计时器
      taskStartTime.value = startResponse.startTime ? new Date(startResponse.startTime) : new Date()
      startTimeUpdateTimer()

      // 更新时间估计数据
      if (startResponse.expectedTotalTime !== undefined && startResponse.expectedTotalTime !== null) {
        // 后端返回的是秒数（数字），格式化为可读文本
        const seconds = Number(startResponse.expectedTotalTime)
        if (seconds > 0) {
          if (seconds < 60) estimatedTime.value = `${Math.floor(seconds)}秒`
          else if (seconds < 3600) estimatedTime.value = `${Math.floor(seconds / 60)}分钟`
          else estimatedTime.value = `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分钟`
        } else {
          estimatedTime.value = '--'
        }
      }
      if (startResponse.expectedCompleteTime !== undefined && startResponse.expectedCompleteTime !== null && String(startResponse.expectedCompleteTime).trim() !== '') {
        expectedCompleteTime.value = String(startResponse.expectedCompleteTime)
      }
      
      addLog({ content: '测试任务已成功启动', level: 'info' })
      console.log('[startTest] 测试启动成功，返回true')
      
      return true
    } catch (error) {
      isExecuting.value = false
      console.error('[startTest] 启动测试失败:', error)
      addLog({ content: `启动测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
      // 不再使用 alert 弹窗
      console.log('[startTest] 返回false，将触发步骤回退')
      return false
    }
  }

  const handleOpenEditModal = async (testCase: TestCase) => {
    editingTestCase.value = testCase
    
    const normalized = normalizeTestCaseConfig(testCase.config || {})
    const testCaseType = (testCase as any).test_type || (testCase as any).testType || 'e2e'
    
    formData.value = {
      id: testCase.id,
      name: testCase.name || '',
      group: testCase.groupName || '',
      groupId: testCase.groupId || '',
      description: testCase.description || '',
      tags: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name),
      tagsInput: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name).join(', '),
      config: normalized as TestCaseFormData['config'],
      algorithmType: (testCase as any).algorithmType || (testCase as any).algorithm_type || '',
      test_type: testCaseType as 'api' | 'e2e',
      // 新设计：algorithm_params 独立列（后端返回驼峰 algorithmParams）
      algorithm_params: Array.isArray((testCase as any).algorithmParams || (testCase as any).algorithm_params)
        ? ((testCase as any).algorithmParams || (testCase as any).algorithm_params)
        : [],
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
    const device = devices.value.find((d) => String(d.id) === String(deviceId))
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

  const saveReport = async () => {
    try {
      const reportId = report.value?.id
      if (!reportId) {
        throw new Error('无法保存报告：报告ID为空')
      }
      await reportsApi.update(reportId, report.value)
      isEditingReport.value = false
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '保存成功',
        content: '报告已成功保存',
        confirmText: '确定',
        cancelText: ''
      })
    } catch (error) {
      console.error('保存报告失败:', error)
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '保存失败',
        content: `保存报告失败: ${error instanceof Error ? error.message : String(error)}`,
        confirmText: '确定',
        cancelText: '',
        danger: true
      })
    }
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
    fetchTagView
  }
}
