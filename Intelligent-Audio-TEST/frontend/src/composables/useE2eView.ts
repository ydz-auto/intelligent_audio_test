import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { tasksApi, reportsApi, testcasesApi, groupsApi } from '../utils/api'
import { useTestCaseCard } from './useTestCaseCard'
import { useDeviceManagement } from './useDeviceManagement'
import { useTaskProgress } from './useTaskProgress'
import { useModalControl, MODAL_TYPES } from './useModal'
import { useDeleteConfirm } from './useDeleteConfirm'
import { useE2eTest } from './useE2eTest'
import { useTestCaseStore } from '../store/testCaseStore'
import { type Report, type Log, type TestCase } from '../shared/types'
import { loadAlgorithmDetail } from './useAlgorithmConfig'

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
    showTestCaseModal, 
    showGroupModal, 
    showImportModal, 
    showExportModal, 
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
    handleModalClose,
    handleModalSave,
    handleTestCaseAction
  } = useTestCaseCard();

  const modalManager = useModalControl()
  const { isLoading: testCasesLoading, e2eTestCaseGroups, e2eTestCases, tags, initializeE2eTests, paginationInfo } = useE2eTest()

  const currentStep = ref(0)
  const currentTaskId = ref<number | null>(null)
  const isExecuting = ref(false)
  const isPaused = ref(false)
  const isControlling = ref(false)
  const activeTab = ref('cases')
  const concurrentTasks = ref(4)
  const isEditingReport = ref(false)
  const isEditingConclusion = ref(false)
  const report = ref<any>({ title: '端到端测试报告', conclusion: '', analysis: '', summary: {} })
  const analysisContent = ref('')
  const reportTables = ref([])
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const taskName = ref('')
  const taskStartTime = ref<Date | null>(null)
  const taskElapsedTimeDisplay = ref('00:00:00')
  let timeUpdateTimer: ReturnType<typeof setInterval> | null = null

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
      await fetchReport()
      if (report.value?.id) {
        router.push({ name: 'reportView', params: { id: report.value.id } })
      } else {
        currentStep.value = 4
      }
    },
    onFailed: (data: any) => {
      isExecuting.value = false
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
      // 先调用生成报告接口
      const generateResponse = await reportsApi.generateTaskReport(currentTaskId.value)
      console.log('[fetchReport] 生成报告响应:', generateResponse)
      
      // 获取新生成的报告
      const response = await reportsApi.getOne(generateResponse.id)
      if (response) {
        report.value = response
        analysisContent.value = response.analysis || ''
        reportTables.value = response.tables || []
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
      
      // 更新时间估计数据
      if (startResponse.expectedTotalTime) {
        estimatedTime.value = startResponse.expectedTotalTime
      }
      if (startResponse.expectedCompleteTime) {
        expectedCompleteTime.value = startResponse.expectedCompleteTime
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

  const pauseTest = async () => {
    if (!currentTaskId.value) {
      addLog({ content: '无法暂停测试：当前任务ID为空', level: 'error' })
      return
    }
    if (isControlling.value) return

    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '暂停测试',
      content: '确定要暂停当前的测试任务吗？',
      confirmText: '暂停',
      cancelText: '取消'
    })

    if (confirmed) {
      isControlling.value = true
      try {
        await tasksApi.control(currentTaskId.value, 'pause')
        isPaused.value = true
        addLog({ content: '测试任务已暂停', level: 'warn' })
      } catch (error) {
        console.error('暂停测试失败:', error)
        addLog({ content: `暂停测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
      } finally {
        isControlling.value = false
      }
    }
  }

  const resumeTest = async () => {
    if (!currentTaskId.value) {
      addLog({ content: '无法恢复测试：当前任务ID为空', level: 'error' })
      return
    }
    if (isControlling.value) return

    isControlling.value = true
    try {
      await tasksApi.control(currentTaskId.value, 'resume')
      isPaused.value = false
      addLog({ content: '测试任务已恢复', level: 'info' })
    } catch (error) {
      console.error('恢复测试失败:', error)
      addLog({ content: `恢复测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
    } finally {
      isControlling.value = false
    }
  }

  const stopTest = async () => {
    if (!currentTaskId.value) {
      addLog({ content: '无法停止测试：当前任务ID为空', level: 'error' })
      return
    }
    if (isControlling.value) return

    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '停止测试',
      content: '确定要停止当前的测试任务吗？停止后将无法恢复。',
      confirmText: '停止测试',
      cancelText: '取消',
      danger: true
    })

    if (confirmed) {
      isControlling.value = true
      try {
        await tasksApi.stop(currentTaskId.value)
        isExecuting.value = false
        addLog({ content: '测试任务已停止', level: 'warn' })
      } catch (error) {
        console.error('停止测试失败:', error)
        addLog({ content: `停止测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
      } finally {
        isControlling.value = false
      }
    }
  }

  const handleOpenEditModal = (testCase: TestCase) => {
    editingTestCase.value = testCase
    // 转换testCase对象为TestCaseFormData格式
    formData.value = {
      id: testCase.id, // 修复：添加id属性，确保编辑时能正确识别用例
      name: testCase.name,
      description: testCase.description,
      type: testCase.type,
      config: testCase.config || {
        backgroundNoise: { audioId: null, spl: null, deviceId: null },
        audios: [],
        dimensions: { api: [], e2e: [] }
      },
      groupId: testCase.groupId,
      group: testCase.groupName,
      tags: Array.isArray(testCase.tags) ? 
        testCase.tags.map(tag => typeof tag === 'string' ? tag : tag.name) : 
        [],
      tagsInput: Array.isArray(testCase.tags) ? 
        testCase.tags.map(tag => typeof tag === 'string' ? tag : tag.name).join(', ') : 
        '',
      translationDirectionId: testCase.translationDirectionId,
      algorithmType: testCase.algorithmType,
      algorithmParams: testCase.algorithmParams
    }
    showTestCaseModal.value = true
  }

  // 算法相关
  const algorithmList = ref<any[]>([])
  const selectedAlgorithmType = ref<string>('')
  const algorithmModalVisible = ref(false)
  const algorithmModalMode = ref<'list' | 'create' | 'edit'>('list')
  const algorithmEditData = ref<any>(null)
  const algorithmSearchQuery = ref('')

  const filteredAlgorithmList = computed(() => {
    if (!algorithmSearchQuery.value.trim()) {
      return algorithmList.value
    }
    const query = algorithmSearchQuery.value.toLowerCase().trim()
    return algorithmList.value.filter((algo: any) => 
      algo.name?.toLowerCase().includes(query) ||
      algo.group_name?.toLowerCase().includes(query) ||
      algo.value?.toLowerCase().includes(query)
    )
  })

  const searchAlgorithms = () => {
    // 搜索逻辑通过 computed 属性 filteredAlgorithmList 自动处理
  }

  const loadAlgorithms = async () => {
    try {
      const response = await fetch('/api/v1/algorithm/options')
      const result = await response.json()
      if (result.success) {
        algorithmList.value = result.data.algorithms || []
      }
    } catch (error) {
      console.error('加载算法列表失败:', error)
      algorithmList.value = []
    }
  }

  const selectAlgorithm = async (algorithmType: string) => {
    if (selectedAlgorithmType.value === algorithmType) {
      selectedAlgorithmType.value = ''
      await initializeE2eTests()
    } else {
      selectedAlgorithmType.value = algorithmType || ''
      await initializeE2eTests(algorithmType || undefined)
    }
  }

  const getAlgorithmName = (type: string) => {
    const algorithm = algorithmList.value.find((a: any) => a.value === type)
    return algorithm?.name || type || '未知算法'
  }

  const openAlgorithmModal = () => {
    algorithmModalMode.value = 'list'
    algorithmEditData.value = null
    algorithmModalVisible.value = true
  }

  const openCreateAlgorithmModal = () => {
    algorithmModalMode.value = 'create'
    algorithmEditData.value = null
    algorithmModalVisible.value = true
  }

  const openEditAlgorithmModal = (algorithm: any) => {
    algorithmModalMode.value = 'edit'
    algorithmEditData.value = algorithm
    algorithmModalVisible.value = true
  }

  const openAlgorithmConfigModal = async (algorithm: any) => {
    const detail = await loadAlgorithmDetail(algorithm.value)
    if (detail) {
      algorithmEditData.value = detail
    } else {
      algorithmEditData.value = algorithm
    }
    algorithmModalMode.value = 'edit'
    algorithmModalVisible.value = true
  }

  const closeAlgorithmModal = () => {
    algorithmModalVisible.value = false
  }

  // 根据算法类型过滤设备
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
        await initializeE2eTests();
      }
      handleModalClose();
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
        await initializeE2eTests();
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
        await initializeE2eTests();
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

  const toggleEditReport = () => { isEditingReport.value = !isEditingReport.value }
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
  const cancelEditReport = () => { isEditingReport.value = false }
  const toggleEditConclusion = () => {
    isEditingConclusion.value = !isEditingConclusion.value
  }
  const cancelEditConclusion = () => {
    isEditingConclusion.value = false
  }
  const saveConclusion = async (content: string) => {
    report.value.conclusion = content
    report.value.analysis = content
    const reportId = report.value?.id
    if (reportId) {
      await reportsApi.update(reportId, report.value)
    }
    analysisContent.value = content
    isEditingConclusion.value = false
  }
  const exportResults = (format: string) => { console.log('Exporting as', format) }
  const publishReport = () => { console.log('Publishing report') }
  const startNewTest = () => {
    currentStep.value = 1
    currentTaskId.value = null
    isExecuting.value = false
    resetProgress()
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
    showTestCaseModal,
    showGroupModal,
    showImportModal,
    showExportModal,
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
    handleModalClose,
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
    openEditAlgorithmModal,
    openAlgorithmConfigModal,
    closeAlgorithmModal,
    algorithmModalVisible,
    algorithmModalMode,
    algorithmEditData,
    algorithmSearchQuery,
    filteredAlgorithmList,
    searchAlgorithms
  }
}
