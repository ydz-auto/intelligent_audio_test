import { ref, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { transformTestCaseStatus } from '../../utils/statusUtils'
import { formatDurationText } from '../../utils/durationFormat'
import { TaskStatus, ExecutionStatus, EvaluationStatus, FINISHED_STATUSES, type TaskStatusType } from '../../domain/enums'
import { taskChannelPort } from './taskChannelPort'
import { tasksPort } from './tasksPort'
import type {
  TaskProgress,
  TaskProgressCaseItem,
  AssociatedCase,
  APIResource,
} from '../../domain/model/taskProgress'
import type { Log } from '../../domain'

/** HTTP 兜底轮询间隔（INT-203：WS 断开降级轮询；VITE_TASK_PROGRESS_POLL_INTERVAL_MS 可配，默认 5s） */
const parsePositiveInt = (raw: unknown, fallback: number): number => {
  const n = Number(raw)
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : fallback
}
const FALLBACK_POLL_INTERVAL_MS = parsePositiveInt(import.meta.env.VITE_TASK_PROGRESS_POLL_INTERVAL_MS, 5000)

interface TaskProgressOptions {
  currentTaskId: Ref<string | number | null>;
  onCompleted?: (data: TaskProgress) => void;
  onFailed?: (data: TaskProgress) => void;
}

export function useTaskProgress(options: TaskProgressOptions) {
  const { currentTaskId, onCompleted, onFailed } = options

  const progressPercentage = ref(0)
  const completedTests = ref(0)
  const inProgressTests = ref(0)
  const pendingTests = ref(0)
  const executionFailedTests = ref(0)
  const evaluationFailedTests = ref(0)
  const totalTestCases = ref(0)
  const taskStatus = ref<TaskStatusType>(TaskStatus.PENDING)
  // INT-301：任务级执行/评估双状态（task_progress 携带，实时更新双徽章）
  const taskExecutionStatus = ref<string>('')
  const taskEvaluationStatus = ref<string>('')
  const elapsedTime = ref('0分钟')
  const estimatedTime = ref('')
  const expectedCompleteTime = ref('--')
  const logs = ref<Log[]>([])
  const associatedCases = ref<AssociatedCase[]>([])
  const apiResources = ref<APIResource[]>([])
  const hasCalledCompletedCallback = ref(false)
  const hasCalledFailedCallback = ref(false)
  /** WS 断开降级轮询进行中（供视图展示降级提示） */
  const isProgressPolling = ref(false)

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

  const handleTaskProgress = async (progressData: TaskProgress, source: 'socket' | 'http' = 'socket') => {
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

    // INT-301：双状态实时更新（评估推进只落评估侧；执行侧仅显式携带时覆盖）
    if (progressData.evaluationStatus) {
      taskEvaluationStatus.value = progressData.evaluationStatus
    }
    if (progressData.executionStatus) {
      taskExecutionStatus.value = progressData.executionStatus
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
      elapsedTime.value = formatDurationText(progressData.usedTime) || '0分钟'
    }
    if (progressData.usedTime === '0') {
      elapsedTime.value = '0分钟'
    }

    // null 表示该通道无此字段（如 HTTP 轮询），保持现值不清空
    if (progressData.expectedTotalTime !== undefined && progressData.expectedTotalTime !== null) {
      const nextEstimated = formatDurationText(progressData.expectedTotalTime)
      if (nextEstimated !== estimatedTime.value) {
        estimatedTime.value = nextEstimated
      }
    }

    if (progressData.expectedCompleteTime !== undefined && progressData.expectedCompleteTime !== null) {
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
    } else if (source === 'socket') {
      // adapter 已把 null/undefined 归一为空数组，此处不再感知原始 payload；
      // HTTP 兜底通道无资源数据，不清空最近一次 Socket 快照
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
    taskExecutionStatus.value = ''
    taskEvaluationStatus.value = ''
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
  let unsubscribeConnection: (() => void) | undefined

  // ── INT-203：WS 断开 → HTTP 进度接口兜底轮询 ─────────────────────
  // 世代号防僵尸轮询（同 INT-100 审计修复）：tick 为 async，await 期间
  // 重连/卸载/终态停止后恢复，不得再调度下一次轮询。
  let fallbackPollGeneration = 0
  let fallbackPollTimer: ReturnType<typeof setTimeout> | null = null
  let fallbackPollInFlight = false

  const stopFallbackPolling = () => {
    fallbackPollGeneration++
    if (fallbackPollTimer !== null) {
      clearTimeout(fallbackPollTimer)
      fallbackPollTimer = null
    }
    if (isProgressPolling.value) {
      isProgressPolling.value = false
    }
  }

  const scheduleFallbackTick = (generation: number) => {
    if (generation !== fallbackPollGeneration) return
    fallbackPollTimer = setTimeout(() => {
      fallbackPollTimer = null
      void runFallbackTick(generation)
    }, FALLBACK_POLL_INTERVAL_MS)
  }

  const runFallbackTick = async (generation: number) => {
    if (generation !== fallbackPollGeneration) return
    if (fallbackPollInFlight) {
      scheduleFallbackTick(generation)
      return
    }
    fallbackPollInFlight = true
    let reachedTerminal = false
    try {
      const taskId = currentTaskId.value
      if (taskId) {
        const progress = await tasksPort.getProgress(taskId)
        if (generation === fallbackPollGeneration) {
          await handleTaskProgress(progress, 'http')
          reachedTerminal = (FINISHED_STATUSES as readonly string[]).includes(progress.status)
        }
      }
    } catch (error) {
      // 单次轮询失败不终止降级（服务重启窗口），下个周期重试
      console.warn('[useTaskProgress] HTTP 进度轮询失败，将在下个周期重试:', error)
    } finally {
      fallbackPollInFlight = false
    }
    if (reachedTerminal) {
      stopFallbackPolling()
      return
    }
    scheduleFallbackTick(generation)
  }

  const startFallbackPolling = () => {
    if (!currentTaskId.value) return
    // isProgressPolling 为当前活跃标志；generation 仅作在途 tick 失效令牌（单调递增）
    if (isProgressPolling.value || fallbackPollTimer !== null) return
    fallbackPollGeneration++
    isProgressPolling.value = true
    addLog({ content: '实时连接已断开，进度已切换为 HTTP 轮询刷新，正在自动重连...', level: 'warn' })
    void runFallbackTick(fallbackPollGeneration)
  }

  const handleConnectionChange = (connected: boolean) => {
    if (connected) {
      stopFallbackPolling()
      // task_log 走房间投递，重连后房间成员关系已随断连清空，须重新订阅
      if (currentTaskId.value) {
        taskChannelPort.subscribeTask(currentTaskId.value)
      }
    } else if (currentTaskId.value) {
      startFallbackPolling()
    }
  }

  onMounted(() => {
    unsubscribeProgress = taskChannelPort.onTaskProgress(handleTaskProgress)
    unsubscribeLog = taskChannelPort.onTaskLog(taskLogHandler)
    unsubscribeConnection = taskChannelPort.onConnectionChange(handleConnectionChange)

    if (currentTaskId.value) {
      taskChannelPort.subscribeTask(currentTaskId.value)
      if (!taskChannelPort.isConnected()) {
        startFallbackPolling()
      }
    }
  })

  // 任务创建晚于挂载（执行页）或挂载时已带任务（详情模态窗）：断连状态下建任务须立即降级
  watch(currentTaskId, (taskId) => {
    if (!taskId) {
      stopFallbackPolling()
      return
    }
    if (!taskChannelPort.isConnected()) {
      startFallbackPolling()
    }
  })

  onUnmounted(() => {
    if (unsubscribeProgress) unsubscribeProgress()
    if (unsubscribeLog) unsubscribeLog()
    if (unsubscribeConnection) unsubscribeConnection()
    stopFallbackPolling()

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
    taskExecutionStatus,
    taskEvaluationStatus,
    elapsedTime,
    estimatedTime,
    expectedCompleteTime,
    logs,
    associatedCases,
    apiResources,
    isProgressPolling,
    resetProgress,
    addLog
  }
}
