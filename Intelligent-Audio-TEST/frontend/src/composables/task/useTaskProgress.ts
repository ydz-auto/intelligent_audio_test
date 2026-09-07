import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { transformTestCaseStatus } from '../../utils/statusUtils'
import { TaskStatus, ExecutionStatus, EvaluationStatus, type TaskStatusType } from '../../domain/enums'
import { taskChannelPort } from './taskChannelPort'
import type {
  TaskProgress,
  TaskProgressCaseItem,
  AssociatedCase,
  APIResource,
} from '../../domain/model/taskProgress'
import type { Log } from '../../domain'

interface TaskProgressOptions {
  testType?: 'API' | 'E2E';
  currentTaskId: Ref<string | number | null>;
  onCompleted?: (data: TaskProgress) => void;
  onFailed?: (data: TaskProgress) => void;
}

export function useTaskProgress(options: TaskProgressOptions) {
  const { testType = 'API', currentTaskId, onCompleted, onFailed } = options

  const progressPercentage = ref(0)
  const completedTests = ref(0)
  const inProgressTests = ref(0)
  const pendingTests = ref(0)
  const executionFailedTests = ref(0)
  const evaluationFailedTests = ref(0)
  const totalTestCases = ref(0)
  const taskStatus = ref<TaskStatusType>(TaskStatus.PENDING)
  const elapsedTime = ref('0分钟')
  const estimatedTime = ref('')
  const expectedCompleteTime = ref('--')
  const logs = ref<Log[]>([])
  const associatedCases = ref<AssociatedCase[]>([])
  const apiResources = ref<APIResource[]>([])
  const hasCalledCompletedCallback = ref(false)
  const hasCalledFailedCallback = ref(false)

  const normalizeMinutesText = (value: any) => {
    if (value === null || value === undefined) return ''
    if (typeof value === 'number' && Number.isFinite(value)) return `${Math.max(0, Math.floor(value))}分钟`
    const str = String(value).trim()
    return str
  }

  const addLog = (logData: any) => {
    const logId = typeof logData.id === 'number' ? logData.id : (Number(logData.id) || 0)
    // 进度日志字段为 message，HTTP 日志通道字段为 content
    const content = logData.message || logData.content || ''

    // 主去重：通过数据库 id 匹配
    if (logId && logs.value.some(log => log.id === logId)) {
      return
    }

    // 后备去重：无 id 时，通过 content + level 匹配最近一条
    if (!logId && logs.value.some(log =>
      log.content === content && log.level === (logData.level || 'info')
    )) {
      return
    }

    let formattedTime = ''
    if (logData.timestamp) {
      try {
        const date = new Date(logData.timestamp)
        if (!isNaN(date.getTime())) {
          formattedTime = date.toLocaleTimeString()
        }
      } catch {
        // ignore
      }
    } else if (logData.time) {
      formattedTime = logData.time
    }

    const newLog: Log = {
      id: logId || Date.now(),
      taskId: logData.taskId ?? currentTaskId.value,
      level: logData.level || 'info',
      content,
      time: formattedTime || new Date().toLocaleTimeString(),
      timestamp: logData.timestamp ? new Date(logData.timestamp).toISOString() : new Date().toISOString(),
      createdAt: new Date().toISOString(),
      testCaseId: logData.testCaseId
    }

    if (newLog.content) {
      logs.value = [...logs.value, newLog]
    }
  }

  const applyCaseCounts = (progress: TaskProgress) => {
    // 重新计算各种状态的用例数量
    let completedCount = 0
    let inProgressCount = 0
    let failedCount = 0
    let pendingCount = 0

    progress.testCases.forEach((transformed) => {
      // 只计算真正完成的用例
      if (transformed.status === TaskStatus.COMPLETED && transformed.executionStatus !== ExecutionStatus.FAILED && transformed.evaluationStatus !== EvaluationStatus.FAILED) {
        completedCount++
      }
      // 计算进行中的用例（真正执行中）
      else if (transformed.status === ExecutionStatus.IN_PROGRESS || transformed.status === EvaluationStatus.CALCULATING) {
        inProgressCount++
      }
      // 计算排队中的用例
      else if (transformed.status === ExecutionStatus.QUEUED) {
        inProgressCount++
      }
      // 计算失败的用例
      else if (transformed.executionStatus === ExecutionStatus.FAILED || transformed.evaluationStatus === EvaluationStatus.FAILED) {
        failedCount++
      }
      // 计算待执行的用例
      else if (transformed.executionStatus === ExecutionStatus.PENDING && transformed.evaluationStatus === EvaluationStatus.PENDING) {
        pendingCount++
      }
    })

    completedTests.value = Math.min(progress.totalCount, Math.max(0, completedCount))
    inProgressTests.value = Math.min(progress.totalCount, Math.max(0, inProgressCount))
    executionFailedTests.value = Math.min(progress.totalCount, Math.max(0,
      progress.testCases.reduce((sum, tc) => sum + (tc.executionStatus === ExecutionStatus.FAILED ? 1 : 0), 0)))
    evaluationFailedTests.value = Math.min(progress.totalCount, Math.max(0,
      progress.testCases.reduce((sum, tc) => sum + (tc.evaluationStatus === EvaluationStatus.FAILED && tc.executionStatus !== ExecutionStatus.FAILED ? 1 : 0), 0)))
    pendingTests.value = Math.max(0, pendingCount)

    // 重新计算总进度，只基于真正完成的用例
    progressPercentage.value = progress.totalCount > 0
      ? Math.min(100, Math.max(0, Math.round((completedTests.value / progress.totalCount) * 100)))
      : 0
  }

  const applyCountFallback = (progress: TaskProgress) => {
    // 没有 testCases 数据时，使用后端提供的计数
    completedTests.value = Math.min(progress.totalCount, Math.max(0, progress.completedCount))
    inProgressTests.value = Math.min(progress.totalCount - completedTests.value, Math.max(0, progress.inProgressCount))
    executionFailedTests.value = Math.min(progress.totalCount, Math.max(0, progress.executionFailedCount))
    evaluationFailedTests.value = Math.min(progress.totalCount, Math.max(0, progress.evaluationFailedCount))

    // 重新计算待执行数量与总进度
    pendingTests.value = Math.max(0, progress.totalCount - completedTests.value - inProgressTests.value
      - executionFailedTests.value - evaluationFailedTests.value)
    progressPercentage.value = progress.totalCount > 0
      ? Math.min(100, Math.max(0, Math.round((completedTests.value / progress.totalCount) * 100)))
      : 0
  }

  const mergeAssociatedCase = (caseItem: TaskProgressCaseItem) => {
    const index = associatedCases.value.findIndex(tc => String(tc.id) === String(caseItem.id))
    if (index === -1) return
    // 创建新对象以确保响应式更新
    const updatedCases = [...associatedCases.value]
    updatedCases[index] = {
      ...updatedCases[index],
      status: caseItem.status,
      executionStatus: caseItem.executionStatus,
      evaluationStatus: caseItem.evaluationStatus,
      duration: caseItem.duration ? caseItem.duration.toString() : updatedCases[index].duration,
      roundProgress: caseItem.roundProgress
        ? { current: caseItem.roundProgress.current, total: caseItem.roundProgress.total }
        : updatedCases[index].roundProgress
    }
    associatedCases.value = updatedCases
  }

  const handleTaskProgress = async (progressData: TaskProgress) => {
    // Socket 通道 payload 已由 taskChannel 转 camelCase Domain
    if (progressData.taskId !== String(currentTaskId.value ?? '')) {
      return
    }

    if (progressData.status) {
      taskStatus.value = progressData.status
      if (progressData.status === TaskStatus.FAILED && onFailed && !hasCalledFailedCallback.value) {
        hasCalledFailedCallback.value = true
        onFailed(progressData)
      } else if (progressData.status === TaskStatus.COMPLETED && onCompleted && !hasCalledCompletedCallback.value) {
        hasCalledCompletedCallback.value = true
        onCompleted(progressData)
      }
    }

    const totalCount = progressData.totalCount || associatedCases.value.length
    progressData.totalCount = totalCount

    if (progressData.testCases.length > 0) {
      progressData.testCases.forEach(tc => {
        const transformed = transformTestCaseStatus(tc) as any
        tc.status = transformed.status
        tc.executionStatus = transformed.executionStatus
        tc.evaluationStatus = transformed.evaluationStatus
        mergeAssociatedCase(tc)
      })
      applyCaseCounts(progressData)
    } else {
      applyCountFallback(progressData)
    }

    if (progressData.usedTime && progressData.usedTime !== elapsedTime.value) {
      elapsedTime.value = normalizeMinutesText(progressData.usedTime) || '0分钟'
    }
    if (progressData.usedTime === '0') {
      elapsedTime.value = '0分钟'
    }

    if (progressData.expectedTotalTime !== undefined) {
      const nextEstimated = normalizeMinutesText(progressData.expectedTotalTime)
      if (nextEstimated !== estimatedTime.value) {
        estimatedTime.value = nextEstimated
      }
    }

    if (progressData.expectedCompleteTime !== undefined) {
      const nextExpectedCompleteTime =
        progressData.expectedCompleteTime === null || String(progressData.expectedCompleteTime).trim() === ''
          ? '--'
          : String(progressData.expectedCompleteTime)
      if (nextExpectedCompleteTime !== expectedCompleteTime.value) {
        expectedCompleteTime.value = nextExpectedCompleteTime
      }
    }

    progressData.logs.forEach(log => {
      addLog(log)
    })

    if (progressData.apiResources.length > 0) {
      apiResources.value = progressData.apiResources.map(resource => ({ ...resource }))
    } else {
      // adapter 已把 null/undefined 归一为空数组，此处不再感知原始 payload
      apiResources.value = []
    }
  }

  const resetProgress = () => {
    progressPercentage.value = 0
    completedTests.value = 0
    inProgressTests.value = 0
    pendingTests.value = 0
    totalTestCases.value = 0
    taskStatus.value = TaskStatus.PENDING
    elapsedTime.value = '0分钟'
    estimatedTime.value = ''
    expectedCompleteTime.value = '--'
    executionFailedTests.value = 0
    evaluationFailedTests.value = 0
    logs.value = []
    associatedCases.value = []
    apiResources.value = []
    hasCalledCompletedCallback.value = false
    hasCalledFailedCallback.value = false
  }

  const taskLogHandler = (taskId: string, log: any) => {
    // payload 已由 taskChannel 拆分，只比对当前任务
    if (taskId === String(currentTaskId.value)) {
      addLog(log)
    }
  }

  let unsubscribeProgress: (() => void) | undefined
  let unsubscribeLog: (() => void) | undefined

  onMounted(() => {
    unsubscribeProgress = taskChannelPort.onTaskProgress(handleTaskProgress)
    unsubscribeLog = taskChannelPort.onTaskLog(taskLogHandler)

    if (currentTaskId.value) {
      taskChannelPort.subscribeTask(currentTaskId.value)
    }
  })

  onUnmounted(() => {
    if (unsubscribeProgress) unsubscribeProgress()
    if (unsubscribeLog) unsubscribeLog()

    if (currentTaskId.value) {
      taskChannelPort.unsubscribeTask(currentTaskId.value)
    }
  })

  return {
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
    resetProgress,
    addLog
  }
}
