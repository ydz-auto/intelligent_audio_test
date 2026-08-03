import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import socketService from '../../utils/socket'
import { transformTestCaseStatus } from '../../utils/statusUtils'
import type { Log } from '../../shared/types'

interface RoundProgress {
  current: number;
  total: number;
}

interface AssociatedCase {
  id: string | number;
  status: string;
  executionStatus: string;
  evaluationStatus: string;
  duration?: string;
  roundProgress?: RoundProgress;
}

interface APIResource {
  id: string | number;
  name: string;
  currentConcurrent: number;
  queueLength: number;
  avgResponseTime: number;
  maxConcurrent: number;
}

interface TaskProgressOptions {
  testType?: 'API' | 'E2E';
  currentTaskId: Ref<string | number | null>;
  onCompleted?: (data: any) => void;
  onFailed?: (data: any) => void;
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
  const taskStatus = ref('pending')
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
    const content = logData.content || logData.message || ''

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
      taskId: logData.taskId || currentTaskId.value,
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

  const handleTaskProgress = async (progressData: any) => {
    console.log('[handleTaskProgress] 收到原始数据:', JSON.stringify(progressData, null, 2))
    
    if (String(progressData.taskId) !== String(currentTaskId.value)) {
      console.log('[handleTaskProgress] taskId 不匹配，跳过处理')
      console.log('  期望:', currentTaskId.value, '实际:', progressData.taskId)
      return
    }

    const timestamp = new Date().toLocaleTimeString()
    console.log(`[${timestamp}] [${testType}测试] 收到进度更新:`, progressData)

    if (progressData.status) {
      taskStatus.value = progressData.status
      if (progressData.status === 'failed' && onFailed && !hasCalledFailedCallback.value) {
        hasCalledFailedCallback.value = true
        onFailed(progressData)
      } else if (progressData.status === 'completed' && onCompleted && !hasCalledCompletedCallback.value) {
        hasCalledCompletedCallback.value = true
        onCompleted(progressData)
      }
    }

    const totalCount = progressData.totalCount || associatedCases.value.length
    totalTestCases.value = totalCount
    console.log('[handleTaskProgress] 更新 totalTestCases:', totalCount)

    // 处理测试用例数据
    if (progressData.testCases) {
      console.log('[handleTaskProgress] 处理 testCases，数量:', progressData.testCases.length)
      
      // 重新计算各种状态的用例数量
      let completedCount = 0
      let inProgressCount = 0
      let failedCount = 0
      let pendingCount = 0
      
      progressData.testCases.forEach((testCaseProgress: any) => {
        const transformed = transformTestCaseStatus(testCaseProgress) as any
        
        // 只计算真正完成的用例
        if (transformed.status === 'completed' && transformed.executionStatus !== 'failed' && transformed.evaluationStatus !== 'failed') {
          completedCount++
        } 
        // 计算进行中的用例（真正执行中）
        else if (transformed.status === 'in_progress' || transformed.status === 'calculating') {
          inProgressCount++
        }
        // 计算排队中的用例
        else if (transformed.status === 'queued') {
          inProgressCount++
        }
        // 计算失败的用例
        else if (transformed.executionStatus === 'failed' || transformed.evaluationStatus === 'failed') {
          failedCount++
        }
        // 计算待执行的用例
        else if (transformed.executionStatus === 'pending' && transformed.evaluationStatus === 'pending') {
          pendingCount++
        }
        
        // 更新关联用例列表
        const caseProgressId = testCaseProgress.caseId || testCaseProgress.id
        const index = associatedCases.value.findIndex(tc => String(tc.id) === String(caseProgressId))
        console.log('[handleTaskProgress] 更新用例', caseProgressId, '在索引', index)
        if (index !== -1) {
          // 创建新对象以确保响应式更新
          const updatedCases = [...associatedCases.value]
          updatedCases[index] = {
            ...updatedCases[index],
            status: transformed.status,
            executionStatus: transformed.executionStatus,
            evaluationStatus: transformed.evaluationStatus,
            duration: testCaseProgress.duration ? testCaseProgress.duration.toString() : updatedCases[index].duration,
            roundProgress: testCaseProgress.roundProgress
              ? {
                  current: testCaseProgress.roundProgress.current,
                  total: testCaseProgress.roundProgress.total,
                }
              : updatedCases[index].roundProgress
          }
          associatedCases.value = updatedCases
        }
      })
      
      // 更新状态计数
      completedTests.value = Math.min(totalCount, Math.max(0, completedCount))
      inProgressTests.value = Math.min(totalCount, Math.max(0, inProgressCount))
      executionFailedTests.value = Math.min(totalCount, Math.max(0, progressData.testCases.reduce((sum: number, tc: any) => {
        return sum + (tc?.executionStatus === 'failed' ? 1 : 0)
      }, 0)))
      evaluationFailedTests.value = Math.min(totalCount, Math.max(0, progressData.testCases.reduce((sum: number, tc: any) => {
        return sum + (tc?.evaluationStatus === 'failed' && tc?.executionStatus !== 'failed' ? 1 : 0)
      }, 0)))
      pendingTests.value = Math.max(0, pendingCount)
      
      // 重新计算总进度，只基于真正完成的用例
      if (totalCount > 0) {
        progressPercentage.value = Math.min(100, Math.max(0, Math.round((completedTests.value / totalCount) * 100)))
      } else {
        progressPercentage.value = 0
      }
      
      console.log('[handleTaskProgress] 重新计算状态计数:')
      console.log('  完成:', completedTests.value)
      console.log('  进行中:', inProgressTests.value)
      console.log('  失败:', executionFailedTests.value + evaluationFailedTests.value)
      console.log('  待执行:', pendingTests.value)
      console.log('  总进度:', progressPercentage.value + '%')
    } else {
      // 如果没有testCases数据，使用提供的计数
      if (progressData.completedCount !== undefined) {
        // 只接受真正完成的数量，不包括失败
        completedTests.value = Math.min(totalCount, Math.max(0, progressData.completedCount))
      }

      if (progressData.inProgressCount !== undefined) {
        inProgressTests.value = Math.min(totalCount - completedTests.value, Math.max(0, progressData.inProgressCount))
      }

      if (progressData.executionFailedCount !== undefined) {
        executionFailedTests.value = Math.min(totalCount, Math.max(0, Number(progressData.executionFailedCount) || 0))
      }

      if (progressData.evaluationFailedCount !== undefined) {
        evaluationFailedTests.value = Math.min(totalCount, Math.max(0, Number(progressData.evaluationFailedCount) || 0))
      }

      // 重新计算待执行数量
      pendingTests.value = Math.max(0, totalCount - completedTests.value - inProgressTests.value - executionFailedTests.value - evaluationFailedTests.value)
      
      // 重新计算总进度
      if (totalCount > 0) {
        progressPercentage.value = Math.min(100, Math.max(0, Math.round((completedTests.value / totalCount) * 100)))
      } else {
        progressPercentage.value = 0
      }
    }

    if (progressData.usedTime && progressData.usedTime !== elapsedTime.value) {
      elapsedTime.value = normalizeMinutesText(progressData.usedTime) || '0分钟'
    }
    if (progressData.usedTime === 0) {
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

    if (progressData.logs && Array.isArray(progressData.logs)) {
      progressData.logs.forEach((log: any) => {
        addLog(log)
      })
    }

    if (progressData.apiResources && Array.isArray(progressData.apiResources)) {
      console.log('[handleTaskProgress] 处理 apiResources，数量:', progressData.apiResources.length)
      apiResources.value = progressData.apiResources.map((resource: any) => ({
        id: resource.id,
        name: resource.name,
        currentConcurrent: resource.currentConcurrent || 0,
        queueLength: resource.queueLength || 0,
        avgResponseTime: resource.avgResponseTime || 0,
        maxConcurrent: resource.maxConcurrent || 5
      }))
    } else if (progressData.apiResources === null || progressData.apiResources === undefined) {
      apiResources.value = []
    }
  }

  const resetProgress = () => {
    progressPercentage.value = 0
    completedTests.value = 0
    inProgressTests.value = 0
    pendingTests.value = 0
    totalTestCases.value = 0
    taskStatus.value = 'pending'
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

  const taskLogHandler = (data: any) => {
    if (String(data.taskId) === String(currentTaskId.value)) {
      addLog(data.log)
    }
  }

  onMounted(() => {
    console.log('[TaskProgress] 正在监听 task_progress 事件，testType:', testType)
    socketService.on('task_progress', handleTaskProgress)

    console.log('[TaskProgress] 正在监听 task_log 事件 (namespace=/ws/logs)')
    socketService.on('task_log', taskLogHandler, '/ws/logs')

    // 订阅当前 task 的日志房间
    if (currentTaskId.value) {
      console.log('[TaskProgress] 订阅 task 日志房间, task_id:', currentTaskId.value)
      socketService.emit('subscribe_task', { task_id: currentTaskId.value }, '/ws/logs')
    }

    console.log('[TaskProgress] Socket 连接状态:', socketService.isConnected)
  })

  onUnmounted(() => {
    console.log('[TaskProgress] 移除 task_progress 事件监听')
    socketService.off('task_progress', handleTaskProgress)

    console.log('[TaskProgress] 移除 task_log 事件监听')
    socketService.off('task_log', taskLogHandler, '/ws/logs')

    // 取消订阅 task 日志房间
    if (currentTaskId.value) {
      socketService.emit('unsubscribe_task', { task_id: currentTaskId.value }, '/ws/logs')
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
