/**
 * apiTest —— API 列表过滤与分页展示（apiList）
 *
 * 负责 API 列表的算法/状态/关键字过滤、分页切片、语音大模型视图提示，
 * 以及分页切换方法（含总数联动 watch）。
 */
import { computed, watch } from 'vue'
import type { Ref } from 'vue'
import type { APIConfig } from '../../domain'
import { ApiEndpointStatus } from '../../domain/enums'

/** API 列表展示模块依赖 */
export interface ApiListDeps {
  apis: Ref<APIConfig[]>;
  apiSearchQuery: Ref<string>;
  apiFilter: Ref<string>;
  selectedAlgorithmType: Ref<string | null>;
  apiCurrentPage: Ref<number>;
  apiPageSize: Ref<number>;
  apiTotalItems: Ref<number>;
  apiTotalPages: Ref<number>;
}

/** 创建 API 列表过滤/分页展示模块 */
export function createApiListModule(deps: ApiListDeps) {
  const { apis, apiSearchQuery, apiFilter, selectedAlgorithmType, apiCurrentPage, apiPageSize, apiTotalItems, apiTotalPages } = deps

  const allFilteredAPIs = computed(() => {
    return apis.value.filter(api => {
      if (!api) return false

      let matchesAlgorithm = true
      if (selectedAlgorithmType.value) {
        matchesAlgorithm = api.algorithmType === selectedAlgorithmType.value
      }

      let matchesStatus = true
      if (apiFilter.value !== 'all') {
        const normalizedStatus = api.status === ApiEndpointStatus.ONLINE ? ApiEndpointStatus.ONLINE : ApiEndpointStatus.OFFLINE
        matchesStatus = normalizedStatus === apiFilter.value
      }

      let matchesSearch = true
      if (apiSearchQuery.value) {
        const query = apiSearchQuery.value.toLowerCase()
        matchesSearch = Boolean(
          (api.name && api.name.toLowerCase().includes(query)) ||
          (api.endpoints && api.endpoints.some((ep: any) => {
            const urlValue = ep.endpoint || '';
            return urlValue.toLowerCase().includes(query);
          }))
        )
      }

      return matchesAlgorithm && matchesStatus && matchesSearch
    })
  })

  // 分页后的API列表
  const filteredAPIs = computed(() => {
    const start = (apiCurrentPage.value - 1) * apiPageSize.value;
    const end = start + apiPageSize.value;
    return allFilteredAPIs.value.slice(start, end);
  })

  const isVoiceLLM = computed(() => selectedAlgorithmType.value === 'voice_llm')

  const stepHints = computed(() => {
    if (!isVoiceLLM.value) return {}
    return {
      caseSelection: 'voice_llm 用例支持多轮对话，每个用例可配置多个轮次的输入文本/音频'
    }
  })

  // 更新总数
  watch(allFilteredAPIs, (newVal) => {
    apiTotalItems.value = newVal.length;
    if (apiCurrentPage.value > apiTotalPages.value && apiTotalPages.value > 0) {
      apiCurrentPage.value = 1;
    }
  }, { immediate: true });

  // 分页方法
  const handleApiPageChange = (page: number) => {
    if (page >= 1 && page <= apiTotalPages.value) {
      apiCurrentPage.value = page;
    }
  };

  const handleApiPageSizeChange = (size: number) => {
    apiPageSize.value = size;
    apiCurrentPage.value = 1;
  };

  const handleApiPrevPage = () => {
    if (apiCurrentPage.value > 1) {
      apiCurrentPage.value--;
    }
  };

  const handleApiNextPage = () => {
    if (apiCurrentPage.value < apiTotalPages.value) {
      apiCurrentPage.value++;
    }
  };

  return {
    allFilteredAPIs,
    filteredAPIs,
    isVoiceLLM,
    stepHints,
    handleApiPageChange,
    handleApiPageSizeChange,
    handleApiPrevPage,
    handleApiNextPage
  }
}
