import { ref, computed, type Ref } from 'vue'
import { tasksApi } from '../../utils/api'
import type { APIConfig, TestCase } from '../../shared/types'

interface UseTaskExecutionOptions {
  testType: 'e2e' | 'api'
  currentTaskId: Ref<string | number | null>
  taskName: Ref<string>
  concurrentTasks: Ref<number>
  selectedTestCaseIds: Ref<(string | number)[]>
  // e2e
  selectedDeviceIds: Ref<(string | number)[]>
  e2eTestCases: Ref<TestCase[]>
  // api
  selectedAPIIds: Ref<(string | number)[]>
  apis: Ref<APIConfig[]>
  testCaseGroups: Ref<Record<string, TestCase[]>>
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
export function useTaskExecution(options: UseTaskExecutionOptions) {
  const {
    testType, currentTaskId, taskName, concurrentTasks,
    selectedTestCaseIds,
    selectedDeviceIds, e2eTestCases,
    selectedAPIIds, apis, testCaseGroups,
    resetProgress, associatedCases, totalTestCases, pendingTests,
    estimatedTime, expectedCompleteTime, addLog, onE2eStart,
  } = options

  const e2eIsExecuting = ref(false)

  /** e2e: 是否可以开始测试 */
  const canStartTest = computed(() => {
    if (testType !== 'e2e') return false
    return selectedDeviceIds.value.length > 0 && !e2eIsExecuting.value
  })

  /** e2e 启动测试 */
  const startE2eTest = async () => {
    if (testType !== 'e2e') return false
    if (!canStartTest.value) return false

    try {
      if (selectedDeviceIds.value.length === 0) {
        throw new Error('请选择至少一个测试设备')
      }

      const selectedCaseIds = selectedTestCaseIds.value.length > 0
        ? selectedTestCaseIds.value
        : e2eTestCases.value.map((c: any) => c.id)

      if (selectedCaseIds.length === 0) {
        throw new Error('没有可用的E2E测试用例')
      }

      e2eIsExecuting.value = true
      resetProgress()

      const payload = {
        name: taskName.value || `E2E测试任务_${new Date().toLocaleString()}`,
        type: 'e2e',
        deviceIds: selectedDeviceIds.value,
        caseIds: selectedCaseIds,
        config: { parallel: true, concurrentTasks: concurrentTasks.value },
      }

      addLog({ content: '正在创建测试任务...', level: 'info' })
      const response = await tasksApi.create(payload)
      currentTaskId.value = response.id

      associatedCases.value = selectedCaseIds.map((id: any) => ({
        id,
        name: e2eTestCases.value.find((c: any) => String(c.id) === String(id))?.name || `用例 ${id}`,
        status: 'pending',
        executionStatus: 'pending',
        evaluationStatus: 'pending',
      }))

      totalTestCases.value = associatedCases.value.length
      pendingTests.value = totalTestCases.value

      addLog({ content: '测试任务已创建，正在启动...', level: 'info' })
      const startResponse = await tasksApi.start(response.id)

      onE2eStart?.(startResponse)

      // 时间估计
      if (startResponse.expectedTotalTime !== undefined && startResponse.expectedTotalTime !== null) {
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
    if (testType !== 'api') return false

    if (selectedTestCaseIds.value.length === 0) {
      addLog({ content: '请至少选择一个测试用例', level: 'warn' })
      return false
    }
    if (selectedAPIIds.value.length === 0) {
      addLog({ content: '请至少选择一个在线API', level: 'warn' })
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

    const nonOnlineApis = selectedApis.filter(a => a.status !== 'online')
    if (nonOnlineApis.length > 0) {
      addLog({ content: `以下API处于离线状态，无法执行测试：${nonOnlineApis.map(a => a.name).join(', ')}`, level: 'warn' })
      return false
    }

    try {
      const taskData = {
        name: taskName.value || 'API测试任务',
        description: '通过API测试任务',
        type: 'api',
        caseIds: selectedTestCaseIds.value,
        apiIds: selectedAPIIds.value,
        tags: [],
      }

      const taskResponse = await tasksApi.create(taskData)
      currentTaskId.value = taskResponse.id

      associatedCases.value = selectedTestCaseIds.value
        .map(id => {
          const allCases = Object.values(testCaseGroups.value as Record<string, TestCase[]>).flat()
          const testCase = allCases.find(tc => String(tc.id) === String(id))
          return testCase ? {
            ...testCase,
            status: 'pending',
            duration: '0',
            executionStatus: 'pending',
            evaluationStatus: 'pending',
          } as any : undefined
        })
        .filter((item): item is any => item !== undefined)

      totalTestCases.value = associatedCases.value.length
      pendingTests.value = totalTestCases.value

      const maxConcurrent = selectedApis.reduce((sum, api) => sum + (api.maxConcurrent || api.currentConcurrent || 5), 0)
      concurrentTasks.value = maxConcurrent

      const startResponse = await tasksApi.start(taskResponse.id)

      if (startResponse.expectedTotalTime) {
        estimatedTime.value = String(startResponse.expectedTotalTime)
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
    if (testType === 'e2e') return startE2eTest()
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
