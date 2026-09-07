/**
 * apiTest —— 生命周期与初始化（lifecycle）
 *
 * 负责页面初始化：加载算法、按算法加载用例、拉取全部测试 API。
 */
import { apisPort } from '@/composables/apiTest/apisPort'
import type { Ref } from 'vue'
import type { APIConfig } from '../../domain'

/** 初始化模块依赖 */
export interface ApiTestLifecycleDeps {
  apis: Ref<APIConfig[]>;
  selectedAlgorithmType: Ref<string | null>;
  loadAlgorithms: () => Promise<void>;
  fetchTestCases: (params?: Record<string, any>) => Promise<any>;
}

/** 创建初始化模块 */
export function createApiTestLifecycleModule(deps: ApiTestLifecycleDeps) {
  const { apis, selectedAlgorithmType, loadAlgorithms, fetchTestCases } = deps

  const initAPITest = async () => {
    await loadAlgorithms()
    const algorithmType = selectedAlgorithmType.value || undefined
    await fetchTestCases({ algorithmType })

    try {
      const apiDataResult = await apisPort.getAll()
      // apisPort.getAll() 始终返回 APIConfig[]（camelCase Domain），无需再兼容分页/裸 data 包装
      apis.value = apiDataResult as APIConfig[]
    } catch (error) {
      console.error('获取API数据失败:', error)
    }
  }

  return {
    initAPITest
  }
}