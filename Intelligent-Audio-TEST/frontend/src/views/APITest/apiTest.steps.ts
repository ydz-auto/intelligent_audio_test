/**
 * apiTest —— 分步导航与任务执行（steps）
 *
 * 负责分步导航（下一步/上一步/跳转）、API 测试任务的创建、校验与启动执行，
 * 以及任务启停控制（暂停/恢复/停止）与执行状态/进度计算属性。
 */
import { computed } from 'vue'
import { tasksPort } from '@/composables/task/tasksPort'
import { useTestControl } from '../../composables/shared/useTestControl'
import { useNotification } from '../../composables/modal/useNotification'
import { TaskStatus, ExecutionStatus, EvaluationStatus, TestType, ApiEndpointStatus, type TaskStatusType } from '@/domain/enums'
import type { AssociatedCase } from '../../domain/model/taskProgress'
import type { Ref } from 'vue'
import type { useTestCaseStore } from '../../store/testCaseStore'
import type { APIConfig, TestCase } from '../../domain'

/** 分步导航模块依赖 */
export interface ApiTestStepsDeps {
  currentStep: Ref<number>;
  selectedTestCaseIds: Ref<(string | number)[]>;
  selectedAPIIds: Ref<(string | number)[]>;
  apis: Ref<APIConfig[]>;
  taskName: Ref<string>;
  concurrentTasks: Ref<number>;
  currentTaskId: Ref<string | number | null>;
  testCaseGroups: Ref<Record<string, TestCase[]>>;
  selectedAlgorithmType: Ref<string | null>;
  testCaseStore: ReturnType<typeof useTestCaseStore>;
  associatedCases: Ref<AssociatedCase[]>;
  totalTestCases: Ref<number>;
  pendingTests: Ref<number>;
  estimatedTime: Ref<string>;
  expectedCompleteTime: Ref<string>;
  taskStatus: Ref<TaskStatusType>;
  progressPercentage: Ref<number>;
}

/** 创建分步导航与任务执行模块 */
export function createApiTestStepsModule(deps: ApiTestStepsDeps) {
  const {
    currentStep,
    selectedTestCaseIds,
    selectedAPIIds,
    apis,
    taskName,
    concurrentTasks,
    currentTaskId,
    testCaseGroups,
    selectedAlgorithmType,
    testCaseStore,
    associatedCases,
    totalTestCases,
    pendingTests,
    estimatedTime,
    expectedCompleteTime,
    taskStatus,
    progressPercentage
  } = deps

  const notification = useNotification()

  const {
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest
  } = useTestControl({
    currentTaskId,
    onStopped: () => {
      taskStatus.value = TaskStatus.STOPPED
    }
  })

  const isExecuting = computed(() => taskStatus.value === TaskStatus.RUNNING || taskStatus.value === TaskStatus.STARTING || taskStatus.value === TaskStatus.PENDING)
  const executionProgress = computed(() => progressPercentage.value)

  const nextStep = async () => {
    if (currentStep.value === 2) {
      try {
        let caseIds: (string | number)[] = []
        if (selectedTestCaseIds.value.length > 0) {
          caseIds = selectedTestCaseIds.value
        } else {
          // 没勾选 → 从后端按筛选条件拉取全量ID
          caseIds = await testCaseStore.fetchCaseIdsByFilter({
            testType: TestType.API,
            algorithmType: selectedAlgorithmType.value || undefined,
          })
        }
        if (caseIds.length === 0) {
          notification.warning('当前筛选条件下没有可用的测试用例，请选择用例或调整筛选条件')
          return
        }

        if (selectedAPIIds.value.length === 0) {
          notification.warning('请至少选择一个在线API')
          return
        }

        const selectedApis = selectedAPIIds.value.map((id) => apis.value.find((a) => String(a?.id) === String(id))).filter(Boolean) as APIConfig[]
        const missingIds = selectedAPIIds.value.filter((id) => !apis.value.some((a) => String(a?.id) === String(id)))
        if (missingIds.length > 0) {
          notification.warning('存在未找到的API，请重新选择')
          return
        }

        const nonOnlineApis = selectedApis.filter((a) => a.status !== ApiEndpointStatus.ONLINE)
        if (nonOnlineApis.length > 0) {
          notification.warning(`以下API处于离线状态，无法执行测试：${nonOnlineApis.map((a) => a.name).join(', ')}`)
          return
        }

        const taskData = {
          name: taskName.value || 'API测试任务',
          description: '通过API测试任务',
          type: TestType.API,
          caseIds: caseIds,
          apiIds: selectedAPIIds.value,
          tags: []
        }

        const taskResponse = await tasksPort.create(taskData)
        const taskId = taskResponse.id
        currentTaskId.value = taskId

        associatedCases.value = caseIds
          .map(id => {
            const allCases = Object.values(testCaseGroups.value as Record<string, TestCase[]>).flat()
            const testCase = allCases.find(tc => String(tc.id) === String(id))
            return testCase ? {
              ...testCase,
              status: TaskStatus.PENDING,
              duration: '0',
              executionStatus: ExecutionStatus.PENDING,
              evaluationStatus: EvaluationStatus.PENDING,
              tags: (testCase.tags || []).map(tag => typeof tag === 'string' ? tag : tag.name)
            } as AssociatedCase : undefined
          })
          .filter((item): item is AssociatedCase => item !== undefined)

        totalTestCases.value = associatedCases.value.length
        pendingTests.value = totalTestCases.value

        const maxConcurrent = selectedApis.reduce((sum, api) => {
          return sum + (api.maxConcurrent || api.currentConcurrent || 5)
        }, 0)
        concurrentTasks.value = maxConcurrent

        const startResponse = await tasksPort.start(taskId)
        console.log('API测试任务已创建并启动:', taskId, startResponse)

        // 更新时间估计数据
        if (startResponse.expectedTotalTime) {
          estimatedTime.value = String(startResponse.expectedTotalTime)
        }
        if (startResponse.expectedCompleteTime) {
          expectedCompleteTime.value = startResponse.expectedCompleteTime
        }
      } catch (error) {
        console.error('创建或启动API测试任务失败:', error)
        // 不再使用 alert 弹窗
      }
    }

    if (currentStep.value < 4) {
      currentStep.value++
    }
  }

  const prevStep = () => {
    if (currentStep.value > 1) {
      currentStep.value--
    }
  }

  const goToStep = (step: number) => {
    currentStep.value = step
  }

  return {
    nextStep,
    prevStep,
    goToStep,
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest,
    isExecuting,
    executionProgress
  }
}