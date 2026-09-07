/**
 * apiTest —— 状态（state）
 *
 * 集中声明 API 测试页的共享 refs（跨 apiList/apiManage/steps/cases/report/lifecycle 复用同一份响应式引用），
 * 以及分步导航常量与 API 分页相关计算属性。
 */
import { ref, computed } from 'vue'
import type { APIConfig } from '../../domain'

/** 分步步骤定义 */
export interface Step {
  number: number;
  title: string;
  description: string;
}

/** 任务结束时间展示（历史遗留接口，保留避免误删） */
export interface WindowWithTaskTime {
  taskExpectedCompleteTimeDisplay?: string
}

/** 创建 API 测试页共享状态（组件级 refs 集合） */
export function createApiTestState() {
  const currentStep = ref(0)
  const steps : Step[] = [
    { number: 0, title: '选择算法', description: '选择测试所使用的算法' },
    { number: 1, title: '选择用例', description: '选择需要执行的测试用例' },
    { number: 2, title: '配置参数', description: '配置执行参数和设备' },
    { number: 3, title: '执行测试', description: '运行测试并监控进度' },
    { number: 4, title: '查看报告', description: '查看和导出测试报告' }
  ]

  const apis = ref<APIConfig[]>([])
  const apiSearchQuery = ref('')
  const apiFilter = ref('all')
  const selectedAPIIds = ref<(string | number)[]>([])
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const activeTab = ref('cases')
  const taskName = ref('API测试任务')
  const concurrentTasks = ref(5)
  const currentTaskId = ref<string | number | null>(null)

  // 分页状态
  const apiCurrentPage = ref(1)
  const apiPageSize = ref(12)
  const apiTotalItems = ref(0)
  const apiTotalPages = computed(() => Math.ceil(apiTotalItems.value / apiPageSize.value))

  return {
    currentStep,
    steps,
    apis,
    apiSearchQuery,
    apiFilter,
    selectedAPIIds,
    selectedTestCaseIds,
    activeTab,
    taskName,
    concurrentTasks,
    currentTaskId,
    apiCurrentPage,
    apiPageSize,
    apiTotalItems,
    apiTotalPages
  }
}
