/**
 * apiTest —— API 管理与选择（apiManage）
 *
 * 负责测试 API 的增删改查（弹窗编排）、连通性测试、健康检查、详情查看与在线选择。
 */
import { apisPort } from '@/composables/apiTest/apisPort'
import { MODAL_TYPES } from '../../composables/modal/useModal'
import { useNotification } from '../../composables/modal/useNotification'
import { generateDeviceFields } from '../../utils/utils'
import { ApiEndpointStatus, TestType } from '@/domain/enums'
import type { Ref } from 'vue'
import type { useModalControl } from '../../composables/modal/useModal'
import type { useDeviceManagement } from '../../composables/device/useDeviceManagement'
import type { APIConfig } from '../../domain'

/** API 管理模块依赖 */
export interface ApiManageDeps {
  apis: Ref<APIConfig[]>;
  apiSearchQuery: Ref<string>;
  apiFilter: Ref<string>;
  selectedAPIIds: Ref<(string | number)[]>;
  modalManager: ReturnType<typeof useModalControl>;
  deviceManagement: ReturnType<typeof useDeviceManagement>;
}

/** 创建 API 管理/选择模块 */
export function createApiManageModule(deps: ApiManageDeps) {
  const notification = useNotification()
  const { apis, apiSearchQuery, apiFilter, selectedAPIIds, modalManager, deviceManagement } = deps

  const openAPIEditModal = (apiData: APIConfig | null = null) => {
    console.log('openAPIEditModal called with apiData:', apiData)
    if (apiData && apiData.id) {
      console.log('Calling editDevice with id:', apiData.id)
      deviceManagement.editDevice(apiData.id, TestType.API)
    } else {
      console.log('Opening add API modal directly')
      modalManager.open(MODAL_TYPES.CRUD_FORM, {
        title: '添加测试API',
        entity: 'device',
        entityName: '测试API',
        mode: 'create',
        deviceType: TestType.API,
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
            // apisPort.getAll() 始终返回 APIConfig[]（camelCase Domain）
            apis.value = apiDataResult as APIConfig[]

            return response
          } catch (error) {
            console.error('API操作失败:', error)
            return null
          }
        }
      })
    }
  }

  const searchAPIs = () => {
    console.log('Searching APIs with query:', apiSearchQuery.value)
  }

  const filterAPIs = () => {
    console.log('Filtering APIs with status:', apiFilter.value)
  }

  const deleteAPI = async (apiId: string | number) => {
    console.log('deleteAPI called with apiId:', apiId)
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除',
      content: '确定要删除该测试API吗？此操作不可恢复。',
      confirmText: '删除',
      cancelText: '取消',
      options: { closable: true },
      onConfirm: async () => {
        try {
          console.log('Deleting API with id:', apiId)
          await apisPort.delete(apiId)
          const apiDataResult = await apisPort.getAll()
          // apisPort.getAll() 始终返回 APIConfig[]（camelCase Domain）
          apis.value = apiDataResult as APIConfig[]
          console.log('API deleted successfully')
        } catch (error) {
          console.error('删除API失败:', error)
        }
      }
    })
  }

  const testAPI = async (apiId: string | number) => {
    if (deviceManagement && typeof deviceManagement.testDeviceConnection === 'function') {
      await deviceManagement.testDeviceConnection(apiId, 'api')
    } else {
      console.warn('设备管理组合式函数中未找到 testDeviceConnection 方法')
    }
  }

  const healthCheck = async (apiId: string | number) => {
    return testAPI(apiId)
  }

  const showAPIDetails = (apiId: string | number) => {
    const api = apis.value.find(a => String(a.id) === String(apiId))
    if (api) {
      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: 'API详情',
        deviceId: String(apiId),
        options: { closable: true, width: '800px' }
      })
    }
  }

  const editAPI = (apiId: string | number) => {
    deviceManagement.editDevice(apiId, 'api')
  }

  const toggleAPISelection = (apiId: string | number) => {
    const api = apis.value.find((a) => String(a?.id) === String(apiId))
    if (!api || api.status !== ApiEndpointStatus.ONLINE) {
      notification.warning('只能选择在线API')
      return
    }
    const index = selectedAPIIds.value.indexOf(apiId)
    if (index === -1) {
      selectedAPIIds.value.push(apiId)
    } else {
      selectedAPIIds.value.splice(index, 1)
    }
  }

  return {
    openAPIEditModal,
    searchAPIs,
    filterAPIs,
    deleteAPI,
    testAPI,
    healthCheck,
    showAPIDetails,
    editAPI,
    toggleAPISelection
  }
}