/**
 * useE2eView —— 任务执行与报告（testRun）
 *
 * 负责分步导航（下一步/上一步/跳转）、E2E 测试任务的创建/校验/启动执行，
 * 以及任务报告的获取与保存。
 */
import { useRouter } from 'vue-router'
import type { ComputedRef, Ref } from 'vue'
import { tasksPort } from '../task/tasksPort'
import { reportsPort } from '../report/reportsPort'
import { viewTaskReport } from '../report/useReportComparison'
import { useTestCaseStore } from '../../store/testCaseStore'
import { MODAL_TYPES } from '../modal/useModal'
import { TaskStatus, TestType, DeviceStatus } from '../../domain/enums'
import type { TestCase } from '../../domain'
import type { AssociatedCase } from '../../domain/model/taskProgress'
import type { ReportData } from '../shared/useTestReport'
import type { useModalControl } from '../modal/useModal'

/** 任务执行与报告模块依赖 */
export interface E2eViewTestRunDeps {
  router: ReturnType<typeof useRouter>
  currentStep: Ref<number>
  currentTaskId: Ref<number | null>
  isExecuting: Ref<boolean>
  isPaused: Ref<boolean>
  taskName: Ref<string>
  concurrentTasks: Ref<number>
  taskStartTime: Ref<Date | null>
  canStartTest: ComputedRef<boolean>
  associatedDevices: ComputedRef<any[]>
  selectedTestCaseIds: Ref<(string | number)[]>
  e2eTestCases: ComputedRef<TestCase[]>
  selectedAlgorithmType: Ref<string | null>
  associatedCases: Ref<AssociatedCase[]>
  totalTestCases: Ref<number>
  pendingTests: Ref<number>
  estimatedTime: Ref<string>
  expectedCompleteTime: Ref<string>
  report: Ref<ReportData>
  analysisContent: Ref<string>
  reportTables: Ref<any[]>
  isEditingReport: Ref<boolean>
  modalManager: ReturnType<typeof useModalControl>
  addLog: (log: Record<string, unknown>) => void
  resetProgress: () => void
  startTimeUpdateTimer: () => void
}

/** 创建任务执行与报告模块 */
export function createE2eViewTestRunModule(deps: E2eViewTestRunDeps) {
  const {
    router,
    currentStep,
    currentTaskId,
    isExecuting,
    isPaused,
    taskName,
    concurrentTasks,
    taskStartTime,
    canStartTest,
    associatedDevices,
    selectedTestCaseIds,
    e2eTestCases,
    selectedAlgorithmType,
    associatedCases,
    totalTestCases,
    pendingTests,
    estimatedTime,
    expectedCompleteTime,
    report,
    analysisContent,
    reportTables,
    isEditingReport,
    modalManager,
    addLog,
    resetProgress,
    startTimeUpdateTimer
  } = deps

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

      const nonOnlineDevices = associatedDevices.value.filter((d: any) => d.status !== DeviceStatus.ONLINE)
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
      
      associatedCases.value = selectedCaseIds.map((id: any) => {
        const tc = e2eTestCases.value.find((c: any) => String(c.id) === String(id))
        return {
          id: id,
          name: tc?.name || `用例 ${id}`,
          groupName: tc?.groupName,
          tags: (tc?.tags || []).map((tag: any) => typeof tag === 'string' ? tag : tag.name),
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

  const nextStep = async () => {
    console.log('[nextStep] 开始执行, currentStep:', currentStep.value)
    if (currentStep.value === 2) {
      const nonOnlineDevices = associatedDevices.value.filter((d: any) => d.status !== DeviceStatus.ONLINE)
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
    nextStep,
    prevStep,
    goToStep,
    startTest,
    fetchReport,
    saveReport
  }
}