/**
 * useE2eExecution —— E2E 任务执行编排（Application 层）
 *
 * 承接 useE2eView 的任务执行职责，视图层只保留状态呈现与交互：
 *   - 任务控制：useTestControl（暂停 / 恢复 / 停止）
 *   - 任务进度：useTaskProgress（socket 进度、日志、关联用例 ReadModel）
 *   - 本地已用时长计时器
 *   - fetchReport / startTest / saveReport 用例编排
 *
 * 外部依赖（路由器、报告、用例列表、设备、模态窗等）由 E2eExecutionContext 注入。
 */
import { ref, computed, type ComputedRef, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { tasksPort } from '../task/tasksPort'
import { reportsPort } from '../report/reportsPort'
import { useTaskProgress } from '../task/useTaskProgress'
import { useTestControl } from '../shared/useTestControl'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import { useTestCaseStore } from '../../store/testCaseStore'
import { viewTaskReport } from '../report/useReportComparison'
import { TaskStatus, TestType } from '../../domain/enums'
import type { TestCase } from '../../domain'
import type { ReportData } from '../shared/useTestReport'

/** E2E 任务执行编排所需的外部依赖 */
export interface E2eExecutionContext {
  /** 路由实例：任务结束后跳转报告页 */
  router: Router
  /** 任务名称（表单输入） */
  taskName: Ref<string>
  /** 并发数（表单输入） */
  concurrentTasks: Ref<number>
  /** 勾选的用例 ID */
  selectedTestCaseIds: Ref<(string | number)[]>
  /** 算法筛选类型 */
  selectedAlgorithmType: Ref<string | null>
  /** 当前算法下的 E2E 用例列表 */
  e2eTestCases: ComputedRef<TestCase[]>
  /** 勾选的关联设备 */
  associatedDevices: ComputedRef<any[]>
  /** 报告 ReadModel（useTestReport 持有） */
  report: Ref<ReportData>
  /** 报告分析内容 */
  analysisContent: Ref<string>
  /** 报告表格数据 */
  reportTables: Ref<any[]>
  /** 报告编辑态 */
  isEditingReport: Ref<boolean>
  /** 模态窗管理器 */
  modalManager: ReturnType<typeof useModalControl>
  /** 任务结束但未产出报告时的视图层回调（回到执行结果步骤） */
  onTaskIncomplete: () => void
}

export function useE2eExecution(context: E2eExecutionContext) {
  const {
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
    onTaskIncomplete
  } = context

  const currentTaskId = ref<string | number | null>(null)
  const isExecuting = ref(false)
  const taskStartTime = ref<Date | null>(null)
  const taskElapsedTimeDisplay = ref('00:00:00')
  let timeUpdateTimer: ReturnType<typeof setInterval> | null = null

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
    onCompleted: async () => {
      isExecuting.value = false
      stopTimeUpdateTimer()
      await fetchReport()
      if (report.value?.id) {
        router.push({ name: 'reportView', params: { id: report.value.id } })
      } else {
        onTaskIncomplete()
      }
    },
    onFailed: () => {
      isExecuting.value = false
      stopTimeUpdateTimer()
      fetchReport()
      if (report.value?.id) {
        router.push({ name: 'reportView', params: { id: report.value.id } })
      } else {
        onTaskIncomplete()
      }
    }
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
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest
  } = useTestControl({
    currentTaskId,
    onStopped: () => {
      isExecuting.value = false
      stopTimeUpdateTimer()
    },
    addLog
  })

  const canStartTest = computed(() => {
    return associatedDevices.value.length > 0 && !isExecuting.value
  })

  const fetchReport = async () => {
    if (!currentTaskId.value) return
    try {
      // 使用 viewTaskReport 统一处理异步报告生成（监听 socket report_generated 事件）
      const reportData = await viewTaskReport({
        id: currentTaskId.value,
        name: taskName.value || 'E2E测试任务',
        type: TestType.E2E,
        status: TaskStatus.COMPLETED,
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

      let selectedCaseIds: (string | number)[] = []
      if (selectedTestCaseIds.value.length > 0) {
        selectedCaseIds = selectedTestCaseIds.value
      } else {
        // 没勾选 → 从后端按筛选条件拉取全量ID
        const store = useTestCaseStore()
        selectedCaseIds = await store.fetchCaseIdsByFilter({
          testType: TestType.E2E,
          algorithmType: selectedAlgorithmType.value || undefined,
        })
      }
      console.log('[startTest] selectedCaseIds数量:', selectedCaseIds.length, 'selectedTestCaseIds:', selectedTestCaseIds.value.length, 'e2eTestCases:', e2eTestCases.value.length)
      if (selectedCaseIds.length === 0) {
        console.log('[startTest] 没有可用的E2E测试用例')
        throw new Error('当前筛选条件下没有可用的E2E测试用例，请选择用例或调整筛选条件')
      }

      const nonOnlineDevices = associatedDevices.value.filter((d: any) => d.status !== 'online')
      if (nonOnlineDevices.length > 0) {
        console.log('[startTest] 有离线设备:', nonOnlineDevices.map((d: any) => d.name))
        throw new Error(`以下设备处于离线状态，无法执行测试：${nonOnlineDevices.map((d: any) => d.name).join(', ')}`)
      }

      isExecuting.value = true
      isPaused.value = false
      resetProgress()
      console.log('[startTest] 准备创建任务')

      const selectedDeviceIds = associatedDevices.value.map((d: any) => d.id)
      console.log('[startTest] 选择的设备数量:', selectedDeviceIds.length)

      const payload = {
        name: taskName.value || `E2E测试任务_${new Date().toLocaleString()}`,
        type: TestType.E2E,
        deviceIds: selectedDeviceIds,
        caseIds: selectedCaseIds,
        config: { parallel: true, concurrentTasks: concurrentTasks.value }
      }

      addLog({ content: '正在创建测试任务...', level: 'info' })
      console.log('[startTest] 发起创建任务API请求')
      const response = await tasksPort.create(payload)
      console.log('[startTest] 任务创建响应:', response)
      currentTaskId.value = response.id

      console.log('[E2E测试] selectedTestCaseIds:', selectedTestCaseIds.value)
      console.log('[E2E测试] e2eTestCases数量:', e2eTestCases.value.length)

      associatedCases.value = selectedCaseIds.map((id) => {
        const tc = e2eTestCases.value.find((c) => String(c.id) === String(id))
        return {
          id: id,
          name: tc?.name || `用例 ${id}`,
          groupName: tc?.groupName,
          tags: (tc?.tags || []).map((tag) => typeof tag === 'string' ? tag : tag.name),
          algorithmType: tc?.algorithmType,
          status: TaskStatus.PENDING,
          executionStatus: TaskStatus.PENDING,
          evaluationStatus: TaskStatus.PENDING
        }
      })

      console.log('[E2E测试] associatedCases:', associatedCases.value)
      totalTestCases.value = associatedCases.value.length
      pendingTests.value = totalTestCases.value

      addLog({ content: '测试任务已创建，正在启动...', level: 'info' })
      const startResponse = await tasksPort.start(response.id)
      console.log('[startTest] 启动任务响应:', startResponse)

      // 设置任务开始时间并启动本地已用时长计时器
      // 注：start 响应不含 startTime，以本地当前时间为准
      taskStartTime.value = new Date()
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

  const saveReport = async () => {
    try {
      const reportId = report.value?.id
      if (!reportId) {
        throw new Error('无法保存报告：报告ID为空')
      }
      await reportsPort.update(reportId, report.value)
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

  return {
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
    resetProgress,
    addLog,
    fetchReport,
    startTest,
    saveReport,
    stopTimeUpdateTimer
  }
}
