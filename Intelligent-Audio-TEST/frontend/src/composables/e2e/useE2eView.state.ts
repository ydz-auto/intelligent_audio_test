/**
 * useE2eView —— 状态（state）
 *
 * 集中声明 E2E 测试页的共享 refs（跨 devices/algorithm/report/cases/testRun/timer 复用同一份引用）。
 */
import { ref } from 'vue'
import { DEFAULT_CONCURRENT_TASKS } from './useE2eView.constants'

/** 创建 E2E 测试页共享状态（组件级 refs 集合） */
export function createE2eViewState() {
  const currentStep = ref(0)
  const currentTaskId = ref<number | null>(null)
  const isExecuting = ref(false)
  const activeTab = ref('cases')
  const concurrentTasks = ref(DEFAULT_CONCURRENT_TASKS)
  const reportTables = ref([])
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const taskName = ref('')
  const taskStartTime = ref<Date | null>(null)
  const taskElapsedTimeDisplay = ref('00:00:00')

  return {
    currentStep,
    currentTaskId,
    isExecuting,
    activeTab,
    concurrentTasks,
    reportTables,
    selectedTestCaseIds,
    taskName,
    taskStartTime,
    taskElapsedTimeDisplay
  }
}

/** E2E 测试页共享状态类型（由工厂推断） */
export type E2eViewState = ReturnType<typeof createE2eViewState>