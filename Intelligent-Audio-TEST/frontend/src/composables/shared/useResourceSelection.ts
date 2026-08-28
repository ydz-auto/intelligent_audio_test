import { ref, computed, watch, type Ref } from 'vue'
import { apisApi } from '../../utils/api'
import { generateDeviceFields } from '../../utils/utils'
import { useDeviceManagement } from '../device/useDeviceManagement'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import type { APIConfig } from '../../shared/types'

interface UseResourceSelectionOptions {
  testType: 'e2e' | 'api'
  selectedAlgorithmType: Ref<string | null>
  addLog: (log: any) => void
}

/**
 * 步骤2 资源选择：e2e 管理测试设备，api 管理被测 API
 * 统一暴露 associatedResources / selectedResourceIds / toggleSelection / handleResourceAction 等
 */
export function useResourceSelection(options: UseResourceSelectionOptions) {
  const { testType, selectedAlgorithmType, addLog } = options
  const modalManager = useModalControl()

  // 共用一个 deviceManagement 实例（e2e -> 'test', api -> 'api'）
  const deviceManagement = useDeviceManagement(testType === 'e2e' ? 'test' : 'api')

  // ============ api 模式独立状态 ============
  const apis = ref<APIConfig[]>([])
  const apiSearchQuery = ref('')
  const apiFilter = ref('all')
  const selectedAPIIds = ref<(string | number)[]>([])

  // api 分页
  const apiCurrentPage = ref(1)
  const apiPageSize = ref(12)
  const apiTotalItems = ref(0)
  const apiTotalPages = computed(() => Math.ceil(apiTotalItems.value / apiPageSize.value))

  // ============ 统一的资源列表 ============
  const associatedResources = computed<any[]>(() => {
    if (testType === 'e2e') {
      return (deviceManagement.devices.value as any[]).filter((d: any) => d.selected)
    }
    return apis.value.filter(api => api && selectedAPIIds.value.map(id => String(id)).includes(String(api.id)))
  })

  const selectedResourceIds = computed<(string | number)[]>(() => {
    if (testType === 'e2e') {
      return associatedResources.value.map((d: any) => d.id)
    }
    return selectedAPIIds.value
  })

  // ============ e2e 算法过滤设备 ============
  const algorithmFilteredDevices = computed(() => {
    if (testType !== 'e2e') return []
    if (!selectedAlgorithmType.value) {
      return deviceManagement.filteredDevices.value
    }
    return (deviceManagement.filteredDevices.value as any[]).filter((device: any) => {
      const supportedAlgorithms = device.supportedAlgorithms
      if (!supportedAlgorithms || !Array.isArray(supportedAlgorithms)) return true
      return supportedAlgorithms.includes(selectedAlgorithmType.value)
    })
  })

  // ============ api 筛选 ============
  const allFilteredAPIs = computed(() => {
    if (testType !== 'api') return []
    return apis.value.filter(api => {
      if (!api) return false

      let matchesAlgorithm = true
      if (selectedAlgorithmType.value) {
        matchesAlgorithm = api.algorithm_type === selectedAlgorithmType.value
      }

      let matchesStatus = true
      if (apiFilter.value !== 'all') {
        const normalizedStatus = api.status === 'online' ? 'online' : 'offline'
        matchesStatus = normalizedStatus === apiFilter.value
      }

      let matchesSearch = true
      if (apiSearchQuery.value) {
        const query = apiSearchQuery.value.toLowerCase()
        matchesSearch = Boolean(
          (api.name && api.name.toLowerCase().includes(query)) ||
          (api.api_endpoints && api.api_endpoints.some((ep: any) => {
            const urlValue = ep.url || ep.endpoint || ''
            return urlValue.toLowerCase().includes(query)
          }))
        )
      }

      return matchesAlgorithm && matchesStatus && matchesSearch
    })
  })

  const filteredAPIs = computed(() => {
    if (testType !== 'api') return []
    const start = (apiCurrentPage.value - 1) * apiPageSize.value
    const end = start + apiPageSize.value
    return allFilteredAPIs.value.slice(start, end)
  })

  // api 分页总数
  if (testType === 'api') {
    watch(allFilteredAPIs, (newVal) => {
      apiTotalItems.value = newVal.length
      if (apiCurrentPage.value > apiTotalPages.value && apiTotalPages.value > 0) {
        apiCurrentPage.value = 1
      }
    }, { immediate: true })
  }

  const handleApiPageChange = (page: number) => {
    if (page >= 1 && page <= apiTotalPages.value) apiCurrentPage.value = page
  }
  const handleApiPageSizeChange = (size: number) => {
    apiPageSize.value = size
    apiCurrentPage.value = 1
  }
  const handleApiPrevPage = () => {
    if (apiCurrentPage.value > 1) apiCurrentPage.value--
  }
  const handleApiNextPage = () => {
    if (apiCurrentPage.value < apiTotalPages.value) apiCurrentPage.value++
  }

  // ============ 资源选择切换 ============
  const handleToggleDeviceSelection = (deviceId: string | number) => {
    if (testType !== 'e2e') return
    const device = (deviceManagement.devices.value as any[]).find(d => String(d.id) === String(deviceId))
    if (device) {
      if (device.status !== 'online') {
        addLog({ content: '只能选择在线设备', level: 'warn' })
        return
      }
      device.selected = device.selected === undefined ? true : !device.selected
    }
  }

  const toggleAPISelection = (apiId: string | number) => {
    if (testType !== 'api') return
    const api = apis.value.find(a => String(a?.id) === String(apiId))
    if (!api || api.status !== 'online') {
      addLog({ content: '只能选择在线API', level: 'warn' })
      return
    }
    const index = selectedAPIIds.value.indexOf(apiId)
    if (index === -1) {
      selectedAPIIds.value.push(apiId)
    } else {
      selectedAPIIds.value.splice(index, 1)
    }
  }

  // 统一的切换方法
  const toggleResourceSelection = (id: string | number) => {
    if (testType === 'e2e') {
      handleToggleDeviceSelection(id)
    } else {
      toggleAPISelection(id)
    }
  }

  // ============ 资源操作（测试/编辑/删除） ============
  const handleResourceAction = ({ actionId, itemId }: { actionId: string; itemId: string | number }) => {
    if (testType === 'e2e') {
      if (actionId === 'test') {
        deviceManagement.testDeviceConnection(itemId, 'test')
      } else if (actionId === 'edit') {
        deviceManagement.editDevice(itemId)
      } else if (actionId === 'delete') {
        deviceManagement.deleteDevice(itemId)
      }
    } else {
      switch (actionId) {
        case 'test':
          testAPI(itemId)
          break
        case 'edit':
          editAPI(itemId)
          break
        case 'delete':
          deleteAPI(itemId)
          break
      }
    }
  }

  // ============ api 增删改 ============
  const openAPIEditModal = (apiData: APIConfig | null = null) => {
    if (apiData && apiData.id) {
      deviceManagement.editDevice(apiData.id, 'api')
    } else {
      modalManager.open(MODAL_TYPES.CRUD_FORM, {
        title: '添加测试API',
        entity: 'device',
        entityName: '测试API',
        mode: 'create',
        deviceType: 'api',
        fields: generateDeviceFields('api'),
        options: { closable: true, width: '800px' },
        onSubmit: async (deviceData: APIConfig, submitMode: 'create' | 'edit') => {
          try {
            let response
            if (submitMode === 'create') {
              response = await apisApi.create(deviceData)
            } else if (submitMode === 'edit' && deviceData.id) {
              response = await apisApi.update(deviceData.id, deviceData)
            }
            const apiDataResult = await apisApi.getAll()
            apis.value = (apiDataResult.items || apiDataResult) as APIConfig[]
            return response
          } catch (error) {
            console.error('[useResourceSelection] API操作失败:', error)
            return null
          }
        },
      })
    }
  }

  const deleteAPI = async (apiId: string | number) => {
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除',
      content: '确定要删除该测试API吗？此操作不可恢复。',
      confirmText: '删除',
      cancelText: '取消',
      options: { closable: true },
      onConfirm: async () => {
        try {
          await apisApi.delete(apiId)
          const apiDataResult = await apisApi.getAll()
          apis.value = (apiDataResult.items || apiDataResult) as APIConfig[]
        } catch (error) {
          console.error('[useResourceSelection] 删除API失败:', error)
        }
      },
    })
  }

  const testAPI = async (apiId: string | number) => {
    if (typeof deviceManagement.testDeviceConnection === 'function') {
      await deviceManagement.testDeviceConnection(apiId, 'api')
    }
  }

  const editAPI = (apiId: string | number) => {
    deviceManagement.editDevice(apiId, 'api')
  }

  // ============ 新增资源入口 ============
  const handleAddResource = () => {
    if (testType === 'e2e') {
      deviceManagement.addDevice()
    } else {
      openAPIEditModal()
    }
  }

  // ============ 初始化 api 列表 ============
  const loadAPIs = async () => {
    if (testType !== 'api') return
    try {
      const apiDataResult = await apisApi.getAll()
      if (Array.isArray(apiDataResult)) {
        apis.value = apiDataResult as APIConfig[]
      } else if (apiDataResult && (apiDataResult as any).items) {
        apis.value = (apiDataResult as any).items as APIConfig[]
      } else if (apiDataResult && (apiDataResult as any).data) {
        apis.value = (apiDataResult as any).data as APIConfig[]
      } else {
        apis.value = []
      }
    } catch (error) {
      console.error('[useResourceSelection] 获取API数据失败:', error)
    }
  }

  return {
    deviceManagement,
    apis,
    apiSearchQuery,
    apiFilter,
    selectedAPIIds,
    filteredAPIs,
    allFilteredAPIs,
    apiCurrentPage,
    apiPageSize,
    apiTotalItems,
    apiTotalPages,
    handleApiPageChange,
    handleApiPageSizeChange,
    handleApiPrevPage,
    handleApiNextPage,
    associatedResources,
    selectedResourceIds,
    algorithmFilteredDevices,
    toggleResourceSelection,
    handleToggleDeviceSelection,
    toggleAPISelection,
    handleResourceAction,
    handleAddResource,
    openAPIEditModal,
    deleteAPI,
    testAPI,
    editAPI,
    loadAPIs,
    // 设备分页（e2e 用）
    deviceSearchQuery: deviceManagement.deviceSearchQuery,
    selectedDeviceStatus: deviceManagement.selectedDeviceStatus,
    currentPage: deviceManagement.currentPage,
    pageSize: deviceManagement.pageSize,
    totalItems: deviceManagement.totalItems,
    totalPages: deviceManagement.totalPages,
    handlePageChange: deviceManagement.handlePageChange,
    handlePageSizeChange: deviceManagement.handlePageSizeChange,
    handlePrevPage: deviceManagement.handlePrevPage,
    handleNextPage: deviceManagement.handleNextPage,
    filteredDevices: deviceManagement.filteredDevices,
    scanDevices: deviceManagement.scanDevices,
    addDevice: deviceManagement.addDevice,
  }
}
