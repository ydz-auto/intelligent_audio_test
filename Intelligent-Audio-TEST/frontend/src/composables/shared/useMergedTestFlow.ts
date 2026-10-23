import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'
import { useTestSteps } from './useTestSteps'
import { useGlobalAlgorithmStore } from '../../store/globalAlgorithmStore'
import { algorithmPort } from '../algorithm/algorithmPort'
import { useTestCaseOps } from './useTestCaseOps'
import { useTaskProgress } from '../task/useTaskProgress'
import { useTestControl } from './useTestControl'
import { useTestTimer } from './useTestTimer'
import { useTestReportOps } from './useTestReportOps'
import { useDeviceManagement } from '../device/useDeviceManagement'
import { apisPort } from '../apiTest/apisPort'
import { tasksPort } from '../task/tasksPort'
import { taskChannelPort } from '../task/taskChannelPort'
import { useTestCaseStore } from '../../store/testCaseStore'
import { normalizeSelectedCaseIds } from './useTestFlow'
import { TaskStatus, DeviceStatus, ApiEndpointStatus, DeviceTabType, ViewMode, type VisibilityType } from '../../domain/enums'
import { getVisibilityPref, setVisibilityPref } from '../visibility/useVisibility'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import type { AlgorithmOption, APIConfig, TestCase, TargetMode, ExecutionMode } from '../../domain'
import { buildCaseDeviceAssignments } from '../../domain/model/task'
import { formatDurationSeconds, formatDurationText } from '../../utils/durationFormat'

/**
 * 测试流程编排层（合并入口 /start-test，INT-486 口径）：
 * 四步单流程——选用例 → 同屏选设备+API → 执行 → 报告；**无「选算法」步骤**
 * （算法切换已全局化，全局算法 store 驱动用例/资源列表自动过滤）。
 * 组合复用各小 composable（用例 / 设备 / API / 进度 / 控制 / 报告），
 * 仅做编排，不包含具体业务逻辑。
 */
export function useMergedTestFlow() {
  // ============ 基础状态 ============
  const taskName = ref('')
  // INT-423/467：新建任务可见性（默认共享；切换时落 localStorage 偏好）
  const taskVisibility = ref<VisibilityType>(getVisibilityPref())
  const activeTab = ref('cases')
  const concurrentTasks = ref(4)
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const currentTaskId = ref<string | number | null>(null)

  // INT-1268/INT-1115：逐目标执行模式（每张设备/API 卡带「并行/串行」单选，默认并行）
  // 缺省（未记录模式项）视为并行；取消选择由 selectionOrder 同步移除并清模式项。
  const targetModes = ref<Record<string, ExecutionMode>>({})
  /** 统一选中顺序（勾选追加/取消移除；target_modes 列表顺序 = 选中顺序 = 串行链顺序） */
  const selectionOrder = ref<Array<{ targetType: 'device' | 'api'; targetId: number }>>([])

  const targetModeKey = (targetType: 'device' | 'api', targetId: number | string) => `${targetType}:${targetId}`

  /** 某目标当前模式（缺省 = 并行；卡片受控值 / 示意图 / 载荷同源） */
  const getTargetMode = (targetType: 'device' | 'api', targetId: number | string): ExecutionMode =>
    targetModes.value[targetModeKey(targetType, targetId)] ?? 'parallel'

  /** 某目标切换模式（即时写 map，示意图 / 载荷同步刷新） */
  const setTargetMode = (targetType: 'device' | 'api', targetId: number | string, mode: ExecutionMode) => {
    targetModes.value = { ...targetModes.value, [targetModeKey(targetType, targetId)]: mode }
  }

  /** 从选中顺序移除某目标（取消选择即清模式项，回默认并行） */
  const removeSelectionEntry = (targetType: 'device' | 'api', targetId: number | string) => {
    selectionOrder.value = selectionOrder.value.filter(
      entry => !(entry.targetType === targetType && String(entry.targetId) === String(targetId))
    )
    const key = targetModeKey(targetType, targetId)
    if (key in targetModes.value) {
      const next = { ...targetModes.value }
      delete next[key]
      targetModes.value = next
    }
  }

  /** target_modes 载荷（保选中顺序；恰好覆盖全部选中目标一次；缺省 = 并行） */
  const targetModesPayload = computed<TargetMode[]>(() =>
    selectionOrder.value.map(({ targetType, targetId }) => ({
      targetType,
      targetId,
      mode: targetModes.value[targetModeKey(targetType, targetId)] ?? 'parallel',
    }))
  )

  /** 串行目标数（任务名称弹窗摘要「串行 {s} 个目标」） */
  const serialCount = computed(() => targetModesPayload.value.filter(item => item.mode === 'serial').length)

  /** INT-423/467：可见性选择器切换 → 记录偏好（各表单新建一致沿用） */
  const handleVisibilityChange = (v: VisibilityType) => {
    taskVisibility.value = v
    setVisibilityPref(v)
  }

  // ============ 全局算法（合并流程：算法切换已全局化，页内不单独选算法） ============
  const globalAlgorithm = useGlobalAlgorithmStore()
  const algorithmList = ref<AlgorithmOption[]>([])
  /** 页内消费用（chip 只读展示 + 列表过滤）；clear 走 × 清空 */
  const selectedAlgorithmType = computed(() => globalAlgorithm.algorithmType)

  async function loadAlgorithms() {
    try {
      const result = await algorithmPort.getOptions()
      algorithmList.value = result?.algorithms ?? []
    } catch (error) {
      console.error('加载算法列表失败:', error)
      algorithmList.value = []
    }
  }

  function getAlgorithmName(type: string | null): string {
    if (!type) return ''
    const algo = algorithmList.value.find(a => a.value === type)
    return algo?.name || type
  }

  // ============ 步骤导航 ============
  const { currentStep, goToStep } = useTestSteps(3)

  // ============ 任务进度（addLog 占位，供后续 composable 使用） ============
  let addLogRef: (log: any) => void = () => {}
  // 报告回调占位（避免 TDZ）
  let reportReadyRef: (() => void) | null = null

  const {
    progressPercentage, completedTests, inProgressTests, pendingTests,
    executionFailedTests, evaluationFailedTests, totalTestCases, taskStatus,
    taskExecutionStatus, taskEvaluationStatus,
    elapsedTime, estimatedTime, expectedCompleteTime, logs, associatedCases,
    apiResources, resetProgress, addLog, isProgressPolling,
  } = useTaskProgress({
    currentTaskId: currentTaskId as any,
    onCompleted: async () => {
      // 终态 → 内联报告（不跳转 reportView，报告装配在步骤三）
      if (reportReadyRef) reportReadyRef()
    },
    onFailed: async () => {
      if (reportReadyRef) reportReadyRef()
    },
  })

  addLogRef = addLog

  // ============ 本地计时器（合并流程展示已用时长） ============
  const {
    setStartTime, startTimeUpdateTimer, stopTimeUpdateTimer,
  } = useTestTimer(elapsedTime)

  // ============ 测试用例操作（用例不分类型，testType='all' 走 store 全量） ============
  const {
    testCaseGroups, tags, tagViewData, tagViewPagination, tagViewLoading, isLoading,
    error, tagViewError,
    e2eTestCases,
    initializeTestCases, fetchTagView, loadMoreTagView, handleTagFilterChange, handleGroupFilterChange,
    handleDeleteGroup, handleDeleteTestCase, handleSaveModal,
    handleOpenAddModal, handleOpenEditModal, showTestCaseDetails: _showTestCaseDetails,
    openCreateGroupModal, openEditGroupModal,
    openImportTestCaseModal, openExportTestCaseModal,
  } = useTestCaseOps({
    testType: 'all',
    selectedAlgorithmType,
    addLog,
  })

  // ============ 设备（被测设备 TEST 页签） ============
  const deviceManagement = useDeviceManagement(DeviceTabType.TEST)

  /** 设备算法过滤（supportedAlgorithms 命中全局算法；无全局算法时全量） */
  const algorithmFilteredDevices = computed(() => {
    const type = selectedAlgorithmType.value
    if (!type) return deviceManagement.filteredDevices.value
    return (deviceManagement.filteredDevices.value as any[]).filter((device: any) => {
      const supportedAlgorithms = device.supportedAlgorithms
      if (!supportedAlgorithms || !Array.isArray(supportedAlgorithms)) return true
      return supportedAlgorithms.includes(type)
    })
  })

  // ============ API（被测 API 列表） ============
  const apis = ref<APIConfig[]>([])
  const apiSearchQuery = ref('')
  const apiFilter = ref(ViewMode.ALL)
  const selectedAPIIds = ref<(string | number)[]>([])
  const apiCurrentPage = ref(1)
  const apiPageSize = ref(12)
  const apiTotalItems = ref(0)
  const apiTotalPages = computed(() => Math.ceil(apiTotalItems.value / apiPageSize.value))

  const allFilteredAPIs = computed(() => {
    return apis.value.filter(api => {
      if (!api) return false
      let matchesAlgorithm = true
      if (selectedAlgorithmType.value) {
        matchesAlgorithm = api.algorithmType === selectedAlgorithmType.value
      }
      let matchesStatus = true
      if (apiFilter.value !== ViewMode.ALL) {
        const normalized = api.status === ApiEndpointStatus.ONLINE ? ApiEndpointStatus.ONLINE : ApiEndpointStatus.OFFLINE
        matchesStatus = normalized === apiFilter.value
      }
      let matchesSearch = true
      if (apiSearchQuery.value) {
        const query = apiSearchQuery.value.toLowerCase()
        matchesSearch = Boolean(
          (api.name && api.name.toLowerCase().includes(query)) ||
          (api.apiUrl && api.apiUrl.toLowerCase().includes(query))
        )
      }
      return matchesAlgorithm && matchesStatus && matchesSearch
    })
  })

  const filteredAPIs = computed(() => {
    const start = (apiCurrentPage.value - 1) * apiPageSize.value
    const end = start + apiPageSize.value
    return allFilteredAPIs.value.slice(start, end)
  })

  const handleApiPageChange = (page: number) => {
    if (page >= 1 && page <= apiTotalPages.value) apiCurrentPage.value = page
  }
  const handleApiPageSizeChange = (size: number) => {
    apiPageSize.value = size
    apiCurrentPage.value = 1
  }
  const handleApiPrevPage = () => {
    if (apiCurrentPage.value > 1) apiCurrentPage.value--
  }
  const handleApiNextPage = () => {
    if (apiCurrentPage.value < apiTotalPages.value) apiCurrentPage.value++
  }

  // ============ 资源选择（设备 selected 标志 + API id 集） ============
  const handleToggleDeviceSelection = (deviceId: string | number) => {
    const device = (deviceManagement.devices.value as any[]).find(d => String(d.id) === String(deviceId))
    if (device) {
      if (device.status !== DeviceStatus.ONLINE) {
        addLogRef({ content: '只能选择在线设备', level: 'warn' })
        return
      }
      const wasSelected = device.selected === true
      device.selected = wasSelected ? false : true
      if (wasSelected) {
        removeSelectionEntry('device', device.id)
      } else {
        selectionOrder.value.push({ targetType: 'device', targetId: Number(device.id) })
      }
    }
  }

  const toggleAPISelection = (apiId: string | number) => {
    const api = apis.value.find(a => String(a?.id) === String(apiId))
    if (!api || api.status !== ApiEndpointStatus.ONLINE) {
      addLogRef({ content: '只能选择在线API', level: 'warn' })
      return
    }
    const index = selectedAPIIds.value.indexOf(apiId)
    if (index === -1) {
      selectedAPIIds.value.push(apiId)
      selectionOrder.value.push({ targetType: 'api', targetId: Number(apiId) })
    } else {
      selectedAPIIds.value.splice(index, 1)
      removeSelectionEntry('api', apiId)
    }
  }

  /** 统一切换（设备/API 同屏，类型由调用方显式传入，不按 id 猜——避免设备/API id 撞车时分发错） */
  const toggleResourceSelection = (id: string | number, type: 'device' | 'api') => {
    if (type === 'device') {
      handleToggleDeviceSelection(id)
    } else {
      toggleAPISelection(id)
    }
  }

  // 已选设备（selected 标志）
  const associatedResources = computed<any[]>(() =>
    (deviceManagement.devices.value as any[]).filter((d: any) => d.selected)
  )
  const selectedDeviceIds = computed<(string | number)[]>(() =>
    associatedResources.value.map((d: any) => d.id)
  )

  // ============ 资源操作（测试/编辑/删除，类型由调用方显式传入） ============
  const handleResourceAction = ({ actionId, itemId }: { actionId: string; itemId: string | number }, type: 'device' | 'api') => {
    if (type === 'device') {
      if (actionId === 'test') {
        deviceManagement.testDeviceConnection(itemId, 'test')
      } else if (actionId === 'edit') {
        deviceManagement.editDevice(itemId)
      } else if (actionId === 'delete') {
        deviceManagement.deleteDevice(itemId)
      }
    } else {
      switch (actionId) {
        case 'test':
          testAPI(itemId)
          break
        case 'edit':
          editAPI(itemId)
          break
        case 'delete':
          deleteAPI(itemId)
          break
      }
    }
  }

  // ============ API 增删改 ============
  const openAPIEditModal = (apiData: APIConfig | null = null) => {
    if (apiData && apiData.id) {
      deviceManagement.editDevice(apiData.id, 'api')
    } else {
      deviceManagement.addDevice('api', apiData || {})
    }
  }

  const deleteAPI = async (apiId: string | number) => {
    try {
      const modalManager = useModalControl()
      const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '确认删除',
        content: '确定要删除该测试API吗？此操作不可恢复。',
        confirmText: '删除',
        cancelText: '取消',
      })
      if (confirmed) {
        await apisPort.delete(apiId)
        await loadAPIs()
      }
    } catch (error) {
      console.error('[useMergedTestFlow] 删除API失败:', error)
    }
  }

  const testAPI = async (apiId: string | number) => {
    try {
      await apisPort.testConnection(apiId)
    } catch (error) {
      console.error('[useMergedTestFlow] 测试API失败:', error)
    }
  }

  const editAPI = (apiId: string | number) => {
    deviceManagement.editDevice(apiId, 'api')
  }

  // ============ 新增资源入口 ============
  const handleAddResource = (type: 'device' | 'api' = 'device') => {
    if (type === 'device') {
      deviceManagement.addDevice()
    } else {
      openAPIEditModal()
    }
  }

  const scanDevices = (type?: string) => {
    deviceManagement.scanDevices(type || 'test')
  }

  // ============ 加载 API 列表 ============
  const loadAPIs = async () => {
    try {
      const result = await apisPort.getAll()
      apis.value = Array.isArray(result) ? result : []
      apiTotalItems.value = allFilteredAPIs.value.length
      if (apiCurrentPage.value > apiTotalPages.value && apiTotalPages.value > 0) {
        apiCurrentPage.value = 1
      }
    } catch (error) {
      console.error('[useMergedTestFlow] 获取API数据失败:', error)
      apis.value = []
    }
  }

  // ============ 底部双道示意图（INT-1268/INT-1115 §5.2.4：随选中目标 + 每卡模式实时更新） ============
  const deviceNameById = computed(() => {
    const map = new Map<string | number, string>()
    ;(deviceManagement.devices.value as any[]).forEach(d => map.set(d.id, d.name))
    return map
  })
  const deviceTypeById = computed(() => {
    const map = new Map<string | number, string>()
    ;(deviceManagement.devices.value as any[]).forEach(d => map.set(d.id, d.type ?? 'physical'))
    return map
  })
  const apiNameById = computed(() => {
    const map = new Map<string | number, string>()
    apis.value.forEach(a => { if (a && a.id !== undefined) map.set(a.id, a.name) })
    return map
  })

  /** 示意图目标节点（名称/图标类型已解析，组件直接渲染） */
  interface DiagramTarget extends TargetMode {
    name: string
    /** 节点图标类型（physical/http_api/websocket_api=设备类型；api=API 目标） */
    iconKind: string
  }

  /** 单条执行道（设备道 / API 道）：道内并行组 + 串行链 + 道内阶段箭头 */
  interface ExecutionLane {
    targetType: 'device' | 'api'
    parallelTargets: DiagramTarget[]
    serialTargets: DiagramTarget[]
    /** 阶段箭头：该道第一个串行目标前存在并行目标（该道并行完成后串行依次启动） */
    hasStageArrow: boolean
  }

  const buildLane = (targetType: 'device' | 'api', laneTargets: DiagramTarget[]): ExecutionLane => ({
    targetType,
    parallelTargets: laneTargets.filter(t => t.mode === 'parallel'),
    serialTargets: laneTargets.filter(t => t.mode === 'serial'),
    hasStageArrow: laneTargets.findIndex(t => t.mode === 'serial') > 0,
  })

  /** 双道：设备道 / API 道各自独立（互不等待；空道折叠） */
  const executionLanes = computed<ExecutionLane[]>(() => {
    const deviceLane = buildLane('device', targetModesPayload.value
      .filter(t => t.targetType === 'device')
      .map(t => ({
        ...t,
        name: deviceNameById.value.get(t.targetId) ?? `设备 ${t.targetId}`,
        iconKind: deviceTypeById.value.get(t.targetId) ?? 'physical',
      })))
    const apiLane = buildLane('api', targetModesPayload.value
      .filter(t => t.targetType === 'api')
      .map(t => ({
        ...t,
        name: apiNameById.value.get(t.targetId) ?? `API ${t.targetId}`,
        iconKind: 'api',
      })))
    return [deviceLane, apiLane].filter(lane => lane.parallelTargets.length + lane.serialTargets.length > 0)
  })

  const executionDiagramEmpty = computed(() => targetModesPayload.value.length === 0)

  // ============ 任务执行（合并流程：设备 + API 混合） ============
  const testCaseStore = useTestCaseStore()

  const canStartTest = computed(() =>
    selectedTestCaseIds.value.length > 0 &&
    (selectedDeviceIds.value.length > 0 || selectedAPIIds.value.length > 0)
  )

  /** 合并流程启动：设备 + API 同时创建（后端 TaskCreateRequest 接受 device_ids + api_ids） */
  const startMergedTask = async (): Promise<boolean> => {
    try {
      // INT-282：未勾选用例 → 按筛选条件圈定全量
      let caseIds = selectedTestCaseIds.value
      if (caseIds.length === 0) {
        caseIds = await testCaseStore.fetchCaseIdsByFilter({
          algorithmType: selectedAlgorithmType.value || undefined,
        })
      }
      if (caseIds.length === 0) {
        addLogRef({ content: '当前筛选条件下没有可用的测试用例，请选择用例或调整筛选条件', level: 'warn' })
        return false
      }
      const deviceIds = selectedDeviceIds.value
      const apiIds = selectedAPIIds.value
      if (deviceIds.length === 0 && apiIds.length === 0) {
        addLogRef({ content: '请至少选择一台在线设备或一个在线 API', level: 'warn' })
        return false
      }
      const nonOnlineDevices = associatedResources.value.filter((d: any) => d.status !== DeviceStatus.ONLINE)
      if (nonOnlineDevices.length > 0) {
        addLogRef({ content: `以下设备处于离线状态，无法执行测试：${nonOnlineDevices.map((d: any) => d.name).join(', ')}`, level: 'warn' })
        return false
      }
      const nonOnlineApis = selectedAPIIds.value
        .map(id => apis.value.find(a => String(a?.id) === String(id)))
        .filter(Boolean)
        .filter(a => (a as APIConfig).status !== ApiEndpointStatus.ONLINE)
      if (nonOnlineApis.length > 0) {
        addLogRef({ content: `以下 API 处于离线状态，无法执行测试：${(nonOnlineApis as APIConfig[]).map(a => a.name).join(', ')}`, level: 'warn' })
        return false
      }

      resetProgress()
      // 合并任务并发数：API 选中时按其 maxConcurrent 合计，否则默认 4
      const selectedApis = selectedAPIIds.value
        .map(id => apis.value.find(a => String(a?.id) === String(id)))
        .filter(Boolean) as APIConfig[]
      const apiConcurrent = selectedApis.reduce((sum, api) => sum + (api.maxConcurrent || api.currentConcurrent || 5), 0)
      concurrentTasks.value = apiConcurrent > 0 ? apiConcurrent : 4

      addLogRef({ content: '正在创建测试任务...', level: 'info' })
      // INT-1434：用例级被测设备选择（所选用例 × 选中目标；API 未显式 device_type 按端点协议派生）
      const caseDevices = buildCaseDeviceAssignments({
        caseIds,
        deviceIds,
        apis: selectedAPIIds.value
          .map(id => apis.value.find(a => String(a?.id) === String(id)))
          .filter((a): a is APIConfig => !!a)
          .map(a => ({
            id: a.id,
            deviceType: a.deviceType,
            // 端点 URL（对齐 deviceFetching 口径：endpoints[0] 优先，兜底 apiUrl）
            endpointUrl: a.endpoints?.[0]?.endpoint || a.apiUrl || '',
          })),
      })
      const response = await tasksPort.create({
        name: taskName.value || `测试任务_${new Date().toLocaleString()}`,
        visibility: taskVisibility.value,
        caseIds,
        deviceIds,
        apiIds,
        caseDevices,
        algorithmType: selectedAlgorithmType.value || undefined,
        // INT-1268/INT-1115：逐目标执行模式（保选中顺序；缺省并行）；废弃顶层 execution_mode/serial_first
        targetModes: targetModesPayload.value,
        config: { concurrentTasks: concurrentTasks.value },
      })
      currentTaskId.value = response.id
      // INT-737：任务创建后立即订阅任务 socket 房间（在 start 之前），
      // 否则 socket 已连接时 useTaskProgress 的 currentTaskId watch 不订阅、
      // 后端 task_progress/task_log 事件收不到 → 执行步无法推进到报告步。
      taskChannelPort.subscribeTask(response.id)

      associatedCases.value = caseIds.map((id: any) => {
        const allCases = Object.values(testCaseGroups.value as Record<string, TestCase[]>).flat()
        const testCase = allCases.find(tc => String(tc.id) === String(id))
        return {
          id,
          name: testCase?.name || `用例 ${id}`,
          status: TaskStatus.PENDING,
          executionStatus: TaskStatus.PENDING,
          evaluationStatus: TaskStatus.PENDING,
        }
      })
      totalTestCases.value = associatedCases.value.length
      pendingTests.value = totalTestCases.value

      addLogRef({ content: '测试任务已创建，正在启动...', level: 'info' })
      const startResponse = await tasksPort.start(response.id)

      setStartTime()
      startTimeUpdateTimer()

      if (startResponse.expectedTotalTime !== undefined && startResponse.expectedTotalTime !== null) {
        const seconds = Number(startResponse.expectedTotalTime)
        estimatedTime.value = seconds > 0 ? formatDurationSeconds(seconds) : '--'
      }
      if (startResponse.expectedCompleteTime !== undefined && startResponse.expectedCompleteTime !== null && String(startResponse.expectedCompleteTime).trim() !== '') {
        expectedCompleteTime.value = String(startResponse.expectedCompleteTime)
      }

      addLogRef({ content: '测试任务已成功启动', level: 'info' })
      return true
    } catch (error) {
      console.error('[useMergedTestFlow] 创建或启动测试任务失败:', error)
      addLogRef({ content: `创建或启动测试任务失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
      return false
    }
  }

  // ============ 报告操作（testType='merged'，报告装配在步骤三内联） ============
  const {
    report, isEditingReport, isEditingConclusion, analysisContent, reportTables,
    deviceApiComparisonData, caseExecutionData, deviceApiColumns, caseExecutionColumns,
    setReport, toggleEditReport, toggleEditConclusion, cancelEditReport, cancelEditConclusion,
    saveConclusion, exportResults, publishReport, startNewTest,
    fetchReport, saveReport,
  } = useTestReportOps({
    testType: 'merged',
    currentTaskId,
    taskName,
    onReportReady: () => { reportReadyRef?.() },
    onReportFailed: () => { reportReadyRef?.() },
  })

  // 任务终态：拉取报告 → 内联装配（步骤三）；不跳转 reportView
  reportReadyRef = async () => {
    stopTimeUpdateTimer()
    await fetchReport(taskStatus.value === TaskStatus.COMPLETED ? TaskStatus.COMPLETED : TaskStatus.FAILED, progressPercentage.value)
    currentStep.value = 3
  }

  // ============ 测试控制（暂停/恢复/停止） ============
  const {
    isPaused, isControlling, pauseTest, resumeTest, stopTest,
  } = useTestControl({
    currentTaskId: currentTaskId as any,
    onStopped: () => {
      stopTimeUpdateTimer()
    },
    addLog: (log: any) => addLogRef(log),
  })

  // ============ isExecuting 统一 ============
  const isExecuting = computed(() => {
    return (taskStatus.value as string) === TaskStatus.RUNNING || (taskStatus.value as string) === TaskStatus.STARTING || (taskStatus.value as string) === TaskStatus.PENDING
  })

  const executionProgress = computed(() => progressPercentage.value)

  // ============ voice_llm 提示 ============
  const isVoiceLLM = computed(() => selectedAlgorithmType.value === 'voice_llm')
  const voiceLlmHint = computed(() => {
    if (!isVoiceLLM.value) return null
    return 'voice_llm 测试可能需要设备支持：音量控制、导轨控制、打断检测。请确认设备能力后再选择。'
  })
  const stepHints = computed(() => {
    if (!isVoiceLLM.value) return {} as Record<string, string>
    return { caseSelection: 'voice_llm 用例支持多轮对话，每个用例可配置多个轮次的输入文本/音频' }
  })

  // ============ 显示用例详情 ============
  const showTestCaseDetails = (testCaseId: string | number) => {
    _showTestCaseDetails(testCaseId, currentTaskId.value)
  }

  // ============ 更新选中用例 ============
  const updateSelectedCases = (ids: (string | number)[]) => {
    selectedTestCaseIds.value = normalizeSelectedCaseIds(ids)
  }

  // ============ 步骤定义 ============
  const steps = [
    { number: 0, title: '选择用例', description: '勾选要执行的用例集' },
    { number: 1, title: '选择设备/API', description: '同屏选择设备与 API（混合执行）' },
    { number: 2, title: '执行测试', description: '运行测试并监控进度' },
    { number: 3, title: '查看报告', description: '查看和导出测试报告' },
  ]

  // ============ nextStep / prevStep ============
  const nextStep = async () => {
    if (currentStep.value === 0) {
      currentStep.value = 1
      return
    }
    if (currentStep.value === 1) {
      const started = await startMergedTask()
      if (started) currentStep.value = 2
      return
    }
    if (currentStep.value < 3) currentStep.value++
  }

  const prevStep = () => {
    if (currentStep.value > 0) currentStep.value--
  }

  // ============ 初始化 ============
  const initTest = async () => {
    await Promise.all([
      loadAlgorithms(),
      initializeTestCases(selectedAlgorithmType.value || undefined),
      fetchTagView({ testType: undefined, algorithmType: selectedAlgorithmType.value || undefined }),
      loadAPIs(),
    ])
  }

  onMounted(async () => {
    await initTest()
  })

  onUnmounted(() => {
    stopTimeUpdateTimer()
  })

  return {
    // 基础
    currentStep, steps, selectedTestCaseIds, taskName, activeTab, concurrentTasks,
    taskVisibility, handleVisibilityChange,
    currentTaskId,
    // 全局算法（chip 只读 + × 清空）
    globalAlgorithm, algorithmList, selectedAlgorithmType, loadAlgorithms, getAlgorithmName,
    // 用例
    testCaseGroups, tags, tagViewData, tagViewPagination, tagViewLoading, isLoading,
    error, tagViewError,
    fetchTagView, loadMoreTagView, handleTagFilterChange, handleGroupFilterChange,
    handleDeleteGroup, handleDeleteTestCase, handleSaveModal,
    handleOpenAddModal, handleOpenEditModal,
    openCreateGroupModal, openEditGroupModal, openImportTestCaseModal, openExportTestCaseModal,
    updateSelectedCases, showTestCaseDetails,
    // 设备
    deviceManagement, algorithmFilteredDevices,
    associatedDevices: associatedResources, selectedDeviceIds,
    // API
    apis, apiSearchQuery, apiFilter, selectedAPIIds, filteredAPIs, allFilteredAPIs,
    apiCurrentPage, apiPageSize, apiTotalItems, apiTotalPages,
    handleApiPageChange, handleApiPageSizeChange, handleApiPrevPage, handleApiNextPage,
    toggleAPISelection, openAPIEditModal, deleteAPI, testAPI, editAPI, loadAPIs,
    // 资源统一
    toggleResourceSelection, handleResourceAction, handleAddResource, scanDevices,
    // INT-1268/INT-1115：逐目标执行模式（卡片受控 / 载荷 / 示意图同源）
    targetModes, selectionOrder, getTargetMode, setTargetMode,
    targetModesPayload, serialCount, executionLanes, executionDiagramEmpty,
    // 执行
    isExecuting, executionProgress, isPaused, isControlling, pauseTest, resumeTest, stopTest,
    progressPercentage, completedTests, inProgressTests, pendingTests,
    executionFailedTests, evaluationFailedTests, totalTestCases, taskStatus,
    taskExecutionStatus, taskEvaluationStatus,
    elapsedTime, estimatedTime, expectedCompleteTime, logs, associatedCases,
    apiResources, isProgressPolling, canStartTest,
    startMergedTask,
    // 报告
    report, isEditingReport, isEditingConclusion, analysisContent, reportTables,
    deviceApiComparisonData, caseExecutionData, deviceApiColumns, caseExecutionColumns,
    toggleEditReport, saveReport, cancelEditReport, toggleEditConclusion,
    cancelEditConclusion, saveConclusion, exportResults, publishReport, startNewTest,
    // voice_llm
    isVoiceLLM, voiceLlmHint, stepHints,
    // 步骤导航
    goToStep, nextStep, prevStep,
    initTest,
  }
}
