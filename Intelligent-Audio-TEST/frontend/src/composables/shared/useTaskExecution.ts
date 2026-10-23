import { ref, computed, type Ref } from 'vue'
import { tasksPort } from '../task/tasksPort'
import { formatDurationSeconds, formatDurationText } from '../../utils/durationFormat'
import type { APIConfig, TestCase } from '../../domain'
import { TestType, TaskStatus, ApiEndpointStatus, type VisibilityType } from '../../domain/enums'
import { useTestCaseStore } from '../../store/testCaseStore'
import { buildCaseDeviceAssignments } from '../../domain/model/task'

interface UseTaskExecutionOptions {
  testType: typeof TestType[keyof typeof TestType]
  currentTaskId: Ref<string | number | null>
  taskName: Ref<string>
  /** INT-423/467：新建任务可见性（默认 shared；私有仅 owner 可访问） */
  taskVisibility: Ref<VisibilityType>
  // INT-282：未勾选用例时按筛选拉全量回退需要算法筛选条件（对齐基线 apiTest.ts:413-422）
  selectedAlgorithmType: Ref<string | null>
  concurrentTasks: Ref<number>
  selectedTestCaseIds: Ref<(string | number)[]>
  // e2e
  selectedDeviceIds: Ref<(string | number)[]>
  e2eTestCases: Ref<TestCase[]>
  // api
  selectedAPIIds: Ref<(string | number)[]>
  apis: Ref<APIConfig[]>
  testCaseGroups: Ref<Record<string, TestCase[]>>
  // INT-1115：逐目标执行模式（卡片级「并行/串行」；废弃全局 executionMode/serialFirst）
  // 进度相关（由 useTaskProgress 提供）
  resetProgress: () => void
  associatedCases: Ref<any[]>
  totalTestCases: Ref<number>
  pendingTests: Ref<number>
  estimatedTime: Ref<string>
  expectedCompleteTime: Ref<string>
  addLog: (log: any) => void
  // e2e 计时器回调
  onE2eStart?: (startResponse: any) => void
}

/**
 * 任务执行：创建并启动测试任务（e2e/api 差异分支）
 * 不包含步骤导航逻辑，仅负责任务的创建和启动
 */

/** INT-1434：选中 API 的用例级目标——device_type 取显式值，未显式时传端点 URL 供派生（ws/wss → websocket_api） */
function toCaseDeviceApiTargets(apiIds: (string | number)[], apis: APIConfig[]): Array<{ id: string | number; deviceType?: string | null; endpointUrl?: string }> {
  return apiIds
    .map(id => apis.find(a => String(a?.id) === String(id)))
    .filter((a): a is APIConfig => !!a)
    .map(a => ({
      id: a.id,
      deviceType: a.deviceType,
      // 端点 URL（对齐 deviceFetching 口径：endpoints[0] 优先，兜底 apiUrl）
      endpointUrl: a.endpoints?.[0]?.endpoint || a.apiUrl || '',
    }))
}

export function useTaskExecution(options: UseTaskExecutionOptions) {
  const {
    testType, currentTaskId, taskName, taskVisibility, concurrentTasks,
    selectedAlgorithmType,
    selectedTestCaseIds,
    selectedDeviceIds, e2eTestCases,
    selectedAPIIds, apis, testCaseGroups,
    resetProgress, associatedCases, totalTestCases, pendingTests,
    estimatedTime, expectedCompleteTime, addLog, onE2eStart,
  } = options

  const e2eIsExecuting = ref(false)

  /** e2e: 是否可以开始测试（混选：设备或 API 任一选中即可） */
  const canStartTest = computed(() => {
    if (testType !== TestType.E2E) return false
    return (selectedDeviceIds.value.length > 0 || selectedAPIIds.value.length > 0) && !e2eIsExecuting.value
  })

  /** e2e 启动测试 */
  const startE2eTest = async () => {
    if (testType !== TestType.E2E) return false
    if (!canStartTest.value) return false

    try {
      if (selectedDeviceIds.value.length === 0 && selectedAPIIds.value.length === 0) {
        throw new Error('请至少选择一个测试设备或API')
      }

      const selectedCaseIds = selectedTestCaseIds.value.length > 0
        ? selectedTestCaseIds.value
        : e2eTestCases.value.map((c: any) => c.id)

      if (selectedCaseIds.length === 0) {
        throw new Error('没有可用的E2E测试用例')
      }

      e2eIsExecuting.value = true
      resetProgress()

      // INT-1434：用例级被测设备选择（所选用例 × 选中目标；API 未显式 device_type 按端点协议派生）
      const caseDevices = buildCaseDeviceAssignments({
        caseIds: selectedCaseIds,
        deviceIds: selectedDeviceIds.value,
        apis: toCaseDeviceApiTargets(selectedAPIIds.value, apis.value),
      })

      const payload = {
        name: taskName.value || `E2E测试任务_${new Date().toLocaleString()}`,
        // INT-282：显式携带执行口径（对齐 useE2eExecution 基线契约 type:'e2e'；
        // 后端 task.type 已废弃，网关忽略，归类由用例级 device_type 派生）
        type: TestType.E2E,
        // INT-423/467：新建可见性（缺省后端回落 shared）
        visibility: taskVisibility.value,
        // INT-604/INT-1072：混选设备 + API，同任务同时携带 device_ids + api_ids
        deviceIds: selectedDeviceIds.value,
        apiIds: selectedAPIIds.value,
        caseIds: selectedCaseIds,
        // INT-1434：用例级被测设备选择（websocket_api 路由前置；缺省后端派生兜底）
        caseDevices,
        // INT-1115：逐目标执行模式取代全局执行模式——本流无卡片级控件，缺省全并行（不发 target_modes/旧字段）
        config: { concurrentTasks: concurrentTasks.value },
      }

      addLog({ content: '正在创建测试任务...', level: 'info' })
      const response = await tasksPort.create(payload)
      currentTaskId.value = response.id

      associatedCases.value = selectedCaseIds.map((id: any) => ({
        id,
        name: e2eTestCases.value.find((c: any) => String(c.id) === String(id))?.name || `用例 ${id}`,
        status: TaskStatus.PENDING,
        executionStatus: TaskStatus.PENDING,
        evaluationStatus: TaskStatus.PENDING,
      }))

      totalTestCases.value = associatedCases.value.length
      pendingTests.value = totalTestCases.value

      addLog({ content: '测试任务已创建，正在启动...', level: 'info' })
      const startResponse = await tasksPort.start(response.id)

      onE2eStart?.(startResponse)

      // 时间估计（start 契约：秒）
      if (startResponse.expectedTotalTime !== undefined && startResponse.expectedTotalTime !== null) {
        const seconds = Number(startResponse.expectedTotalTime)
        estimatedTime.value = seconds > 0 ? formatDurationSeconds(seconds) : '--'
      }
      if (startResponse.expectedCompleteTime !== undefined && startResponse.expectedCompleteTime !== null && String(startResponse.expectedCompleteTime).trim() !== '') {
        expectedCompleteTime.value = String(startResponse.expectedCompleteTime)
      }

      addLog({ content: '测试任务已成功启动', level: 'info' })
      return true
    } catch (error) {
      e2eIsExecuting.value = false
      console.error('[useTaskExecution] 启动e2e测试失败:', error)
      addLog({ content: `启动测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
      return false
    }
  }

  /** api 启动测试（在 nextStep 内调用） */
  const startApiTask = async () => {
    if (testType !== TestType.API) return false

    // INT-282：未勾选用例 → 从后端按筛选条件拉取全量 ID（大批量测试免逐个勾选，
    // 对齐基线 V9.7.10 apiTest.ts:413-422；/testcases/ids 后端按用例配置形态派生执行口径）
    let caseIds: (string | number)[] = []
    if (selectedTestCaseIds.value.length > 0) {
      caseIds = selectedTestCaseIds.value
    } else {
      const testCaseStore = useTestCaseStore()
      caseIds = await testCaseStore.fetchCaseIdsByFilter({
        testType: TestType.API,
        algorithmType: selectedAlgorithmType.value || undefined,
      })
    }
    if (caseIds.length === 0) {
      addLog({ content: '当前筛选条件下没有可用的测试用例，请选择用例或调整筛选条件', level: 'warn' })
      return false
    }
    if (selectedAPIIds.value.length === 0 && selectedDeviceIds.value.length === 0) {
      addLog({ content: '请至少选择一个在线API或测试设备', level: 'warn' })
      return false
    }

    const selectedApis = selectedAPIIds.value
      .map(id => apis.value.find(a => String(a?.id) === String(id)))
      .filter(Boolean) as APIConfig[]
    const missingIds = selectedAPIIds.value.filter(id => !apis.value.some(a => String(a?.id) === String(id)))
    if (missingIds.length > 0) {
      addLog({ content: '存在未找到的API，请重新选择', level: 'warn' })
      return false
    }

    const nonOnlineApis = selectedApis.filter(a => a.status !== ApiEndpointStatus.ONLINE)
    if (nonOnlineApis.length > 0) {
      addLog({ content: `以下API处于离线状态，无法执行测试：${nonOnlineApis.map(a => a.name).join(', ')}`, level: 'warn' })
      return false
    }

    try {
      // INT-1434：用例级被测设备选择（所选用例 × 选中目标；API 未显式 device_type 按端点协议派生）
      const caseDevices = buildCaseDeviceAssignments({
        caseIds,
        deviceIds: selectedDeviceIds.value,
        apis: toCaseDeviceApiTargets(selectedAPIIds.value, apis.value),
      })

      const taskData = {
        name: taskName.value || 'API测试任务',
        description: '通过API测试任务',
        // INT-282：显式携带执行口径（对齐基线契约 type:'api'）。
        // 注：V9.7.31 后端 task.type 已废弃（差异#2 收尾），网关 TaskCreateRequest
        // extra="ignore" 静默忽略该字段；任务归类由用例级 TaskCase.device_type 派生。
        // 此处显式传递仅为兼容消费方与后端未来恢复 type 列的契约留痕。
        type: TestType.API,
        // INT-423/467：新建可见性（缺省后端回落 shared）
        visibility: taskVisibility.value,
        caseIds,
        apiIds: selectedAPIIds.value,
        // INT-1072：混选 API + 设备，同任务同时携带 api_ids + device_ids
        deviceIds: selectedDeviceIds.value,
        // INT-1434：用例级被测设备选择（websocket_api 路由前置；缺省后端派生兜底）
        caseDevices,
        tags: [],
      }

      const taskResponse = await tasksPort.create(taskData)
      currentTaskId.value = taskResponse.id

      associatedCases.value = caseIds
        .map(id => {
          const allCases = Object.values(testCaseGroups.value as Record<string, TestCase[]>).flat()
          const testCase = allCases.find(tc => String(tc.id) === String(id))
          // INT-282：全量回退时用例列表为分页数据，未在本地命中的 ID 以占位名保底，
          // 保证 totalTestCases 与任务实际用例数一致（对齐同文件 e2e 分支口径）
          return {
            id,
            name: testCase?.name || `用例 ${id}`,
            status: TaskStatus.PENDING,
            duration: '0',
            executionStatus: TaskStatus.PENDING,
            evaluationStatus: TaskStatus.PENDING,
          } as any
        })

      totalTestCases.value = associatedCases.value.length
      pendingTests.value = totalTestCases.value

      const maxConcurrent = selectedApis.reduce((sum, api) => sum + (api.maxConcurrent || api.currentConcurrent || 5), 0)
      concurrentTasks.value = maxConcurrent

      const startResponse = await tasksPort.start(taskResponse.id)

      if (startResponse.expectedTotalTime) {
        estimatedTime.value = formatDurationText(startResponse.expectedTotalTime)
      }
      if (startResponse.expectedCompleteTime) {
        expectedCompleteTime.value = String(startResponse.expectedCompleteTime)
      }
      return true
    } catch (error) {
      console.error('[useTaskExecution] 创建或启动API测试任务失败:', error)
      addLog({ content: `创建或启动API测试任务失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
      return false
    }
  }

  /** 统一启动入口 */
  const startTask = async () => {
    if (testType === TestType.E2E) return startE2eTest()
    return startApiTask()
  }

  return {
    e2eIsExecuting,
    canStartTest,
    startE2eTest,
    startApiTask,
    startTask,
  }
}
