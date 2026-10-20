import { ref, computed, watch, type Ref } from 'vue'
import { apisPort } from '../apiTest/apisPort'
import { generateDeviceFields } from '../../utils/utils'
import { useDeviceManagement } from '../device/useDeviceManagement'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import type { APIConfig } from '../../domain'
import { ViewMode, DeviceStatus, ApiEndpointStatus, DeviceTabType } from '@/domain/enums'

interface UseResourceSelectionOptions {
  testType: 'e2e' | 'api'
  selectedAlgorithmType: Ref<string | null>
  addLog: (log: any) => void
}

/**
 * 步骤2 资源选择：设备 + 被测 API 同屏混选（INT-604/INT-1072）
 * 统一暴露 associatedResources / selectedResourceIds / toggleSelection / handleResourceAction 等
 * 不再按 testType 二选一：物理设备与 API 两列表同时加载、可同时勾选，
 * 创建请求同时携带 device_ids + api_ids（执行模式串行/并行在任务级生效）。
 */
export function useResourceSelection(options: UseResourceSelectionOptions) {
  const { testType, selectedAlgorithmType, addLog } = options
  const modalManager = useModalControl()

  // 物理设备列表（e2e 测试设备页签；api 模式也复用同一实例，混选时设备/API 同屏）
  const deviceManagement = useDeviceManagement(DeviceTabType.TEST)

  // ============ API 列表状态 ============
  const apis = ref<APIConfig[]>([])
  const apiSearchQuery = ref('')
  const apiFilter = ref(ViewMode.ALL)
  const selectedAPIIds = ref<(string | number)[]>([])

  // api 分页
  const apiCurrentPage = ref(1)
  const apiPageSize = ref(12)
  const apiTotalItems = ref(0)
  const apiTotalPages = computed(() => Math.ceil(apiTotalItems.value / apiPageSize.value))

  // ============ 统一的资源列表 ============
  /** 已选物理设备（selected 标记） */
  const associatedDevices = computed<any[]>(() => {
    return (deviceManagement.devices.value as any[]).filter((d: any) => d.selected)
  })

  /** 已选物理设备 id */
  const selectedDeviceIds = computed<(string | number)[]>(() => {
    return associatedDevices.value.map((d: any) => d.id)
  })

  /** 已选被测 API */
  const associatedAPIs = computed<any[]>(() => {
    return apis.value.filter(api => api && selectedAPIIds.value.map(id => String(id)).includes(String(api.id)))
  })

  /** 合并资源列表（设备 + API，执行模式判定 / 步骤三摘要用） */
  const associatedResources = computed<any[]>(() => [...associatedDevices.value, ...associatedAPIs.value])

  /** 合并已选 id（设备 + API） */
  const selectedResourceIds = computed<(string | number)[]>(() => [
    ...selectedDeviceIds.value,
    ...selectedAPIIds.value,
  ])

  // ============ e2e 算法过滤设备 ============
  const algorithmFilteredDevices = computed(() => {
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
    return apis.value.filter(api => {
      if (!api) return false

      let matchesAlgorithm = true
      if (selectedAlgorithmType.value) {
        // APIConfig Domain 已是 camelCase：algorithmType。
        // INT-604/INT-1072：对齐 React（useResourceSelection.ts:88-91）——未声明
        // 算法类型的 API 不被排除（algorithmType 为空视为通配），否则混选在
        // 具体算法下永远只能看到带类型标记的 API。
        matchesAlgorithm = api.algorithmType == null || api.algorithmType === selectedAlgorithmType.value
      }

      let matchesStatus = true
      if (apiFilter.value !== ViewMode.ALL) {
        const normalizedStatus = api.status === ApiEndpointStatus.ONLINE ? ApiEndpointStatus.ONLINE : ApiEndpointStatus.OFFLINE
        matchesStatus = normalizedStatus === apiFilter.value
      }

      let matchesSearch = true
      if (apiSearchQuery.value) {
        const query = apiSearchQuery.value.toLowerCase()
        matchesSearch = Boolean(
          (api.name && api.name.toLowerCase().includes(query)) ||
          (api.endpoints && api.endpoints.some((ep: any) => {
            const urlValue = ep.url || ep.endpoint || ''
            return urlValue.toLowerCase().includes(query)
          }))
        )
      }

      return matchesAlgorithm && matchesStatus && matchesSearch
    })
  })

  const filteredAPIs = computed(() => {
    const start = (apiCurrentPage.value - 1) * apiPageSize.value
    const end = start + apiPageSize.value
    return allFilteredAPIs.value.slice(start, end)
  })

  // api 分页总数
  watch(allFilteredAPIs, (newVal) => {
    apiTotalItems.value = newVal.length
    if (apiCurrentPage.value > apiTotalPages.value && apiTotalPages.value > 0) {
      apiCurrentPage.value = 1
    }
  }, { immediate: true })

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
    const device = (deviceManagement.devices.value as any[]).find(d => String(d.id) === String(deviceId))
    if (device) {
      if (device.status !== DeviceStatus.ONLINE) {
        addLog({ content: '只能选择在线设备', level: 'warn' })
        return
      }
      device.selected = device.selected === undefined ? true : !device.selected
    }
  }

  const toggleAPISelection = (apiId: string | number) => {
    const api = apis.value.find(a => String(a?.id) === String(apiId))
    if (!api || api.status !== ApiEndpointStatus.ONLINE) {
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

  // 统一的切换方法（单网格旧交互兜底：按 testType 走对应网格）
  const toggleResourceSelection = (id: string | number) => {
    if (testType === 'e2e') {
      handleToggleDeviceSelection(id)
    } else {
      toggleAPISelection(id)
    }
  }

  // ============ 资源操作（测试/编辑/删除） ============
  /** 设备网格操作（e2e 分支） */
  const handleDeviceResourceAction = ({ actionId, itemId }: { actionId: string; itemId: string | number }) => {
    if (actionId === 'test') {
      deviceManagement.testDeviceConnection(itemId, 'test')
    } else if (actionId === 'edit') {
      deviceManagement.editDevice(itemId)
    } else if (actionId === 'delete') {
      deviceManagement.deleteDevice(itemId)
    }
  }

  /** API 网格操作（api 分支） */
  const handleApiResourceAction = ({ actionId, itemId }: { actionId: string; itemId: string | number }) => {
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

  /** 统一入口（按 testType 分支；混选视图按网格分别调用上两方法） */
  const handleResourceAction = ({ actionId, itemId }: { actionId: string; itemId: string | number }) => {
    if (testType === 'e2e') {
      handleDeviceResourceAction({ actionId, itemId })
    } else {
      handleApiResourceAction({ actionId, itemId })
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
              response = await apisPort.create(deviceData)
            } else if (submitMode === 'edit' && deviceData.id) {
              response = await apisPort.update(deviceData.id, deviceData)
            }
            const apiDataResult = await apisPort.getAll()
            // apisPort.getAll 已通过 adapter 展平为 Domain 数组（camelCase），无需再取 items
            apis.value = apiDataResult || []
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
          await apisPort.delete(apiId)
          const apiDataResult = await apisPort.getAll()
          // apisPort.getAll 已通过 adapter 展平为 Domain 数组（camelCase），无需再取 items
          apis.value = apiDataResult || []
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

  // ============ 初始化 api 列表（混选：两种模式都加载） ============
  const loadAPIs = async () => {
    try {
      const apiDataResult = await apisPort.getAll()
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
    associatedDevices,
    selectedDeviceIds,
    associatedAPIs,
    algorithmFilteredDevices,
    toggleResourceSelection,
    handleToggleDeviceSelection,
    toggleAPISelection,
    handleDeviceResourceAction,
    handleApiResourceAction,
    handleResourceAction,
    handleAddResource,
    openAPIEditModal,
    deleteAPI,
    testAPI,
    editAPI,
    loadAPIs,
    // 设备分页
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
