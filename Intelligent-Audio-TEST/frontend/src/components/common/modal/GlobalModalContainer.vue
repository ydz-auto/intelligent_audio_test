<template>
  <Teleport to="body">
    <div 
      class="modal-container-wrapper"
      :class="{ 'modal-container-wrapper--active': activeModals.length > 0 }"
    >
      <template v-for="[modalId, modalItem] in activeModals" :key="modalId">
        <BasicModal
          v-if="modalItem && typeof modalItem === 'object'"
          :visible="true"
          :title="modalItem.props?.title || ''"
          :modal-id="modalId"
          :width="modalItem.props?.width || '500px'"
          :max-width="modalItem.props?.maxWidth || '90vw'"
          :max-height="modalItem.props?.maxHeight || '90vh'"
          :closable="modalItem.props?.closable !== false"
          :mask-closable="modalItem.props?.maskClosable === true"
          :show-footer="false"
          @close="handleClose(modalId)"
          @cancel="handleCancel(modalId, $event)"
        >
          <template v-if="modalItem.component">
            <component
              :is="modalItem.component"
              v-bind="{
                ...modalItem.props,
                visible: true,
                modalId: modalId
              }"
              @close="handleClose(modalId)"
              @confirm="(data: any) => {
                console.log('[GlobalModalContainer] confirm事件触发, data:', data);
                // 调用onSave回调（如果存在）
                if (modalItem.props && typeof modalItem.props.onSave === 'function') {
                  console.log('[GlobalModalContainer] 调用onSave回调');
                  try {
                    modalItem.props.onSave(data);
                  } catch (error) {
                    console.error('[GlobalModalContainer] onSave回调执行失败:', error);
                  }
                } else {
                  console.log('[GlobalModalContainer] 无onSave回调');
                }
                modalItem.resolve(data);
                handleClose(modalId);
              }"
              @cancel="(data: any) => {
                console.log('[GlobalModalContainer] cancel事件触发, data:', data);
                modalItem.resolve(false);
                handleClose(modalId);
              }"
              @save="(data: any) => {
                console.log('[GlobalModalContainer] save事件触发, data:', data);
                // 调用onSave回调（如果存在）
                if (modalItem.props && typeof modalItem.props.onSave === 'function') {
                  console.log('[GlobalModalContainer] 调用onSave回调');
                  try {
                    modalItem.props.onSave(data);
                  } catch (error) {
                    console.error('[GlobalModalContainer] onSave回调执行失败:', error);
                  }
                } else {
                  console.log('[GlobalModalContainer] 无onSave回调');
                }
                modalItem.resolve(data);
                handleClose(modalId);
              }"
              @select="(data: any) => {
                console.log('[GlobalModalContainer] select事件触发, data:', data);
                modalItem.resolve(data);
                handleClose(modalId);
              }"
              @selectMultiple="(data: any) => {
                console.log('[GlobalModalContainer] selectMultiple事件触发, data:', data);
                modalItem.resolve(data);
                handleClose(modalId);
              }"
            />
          </template>
          <template v-else>
            <div class="modal-error">
              <p>无法渲染模态框：组件未定义</p>
              <p class="error-details">模态框类型：{{ modalItem.type || '未定义' }}</p>
            </div>
          </template>
        </BasicModal>
      </template>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { getModalManager } from '../../../composables/useModal'
import { type ActiveModal, MODAL_TYPES } from '../../../shared/types'
import BasicModal from './BasicModal.vue'
import { testcasesApi } from '../../../utils/api'
import TestCaseModal from '../test-case/TestCaseModal.vue'
import AddTestCaseModal from '../test-case/AddTestCaseModal.vue'
import ModalConfirm from './ModalConfirm.vue'
import APIEditModal from './APIEditModal.vue'
import DetailViewModal from './DetailViewModal.vue'
import ImportExportModal from './ImportExportModal.vue'
import CRUDFormModal from './CRUDFormModal.vue'
import UploadFileModal from './UploadFileModal.vue'
import URLImportModal from './URLImportModal.vue'
import FolderImportModal from './FolderImportModal.vue'
import ScanDevicesModal from './ScanDevicesModal.vue'
import SPLCalibrationModal from './SPLCalibrationModal.vue'
import GlobalPlaybackDeviceModal from './GlobalPlaybackDeviceModal.vue'
import BatchAlgorithmParamsModal from './BatchAlgorithmParamsModal.vue'
import BatchSPLModal from './BatchSPLModal.vue'
import BatchPlaybackDeviceModal from './BatchPlaybackDeviceModal.vue'
import BatchAdjustGroupModal from './BatchAdjustGroupModal.vue'
import BatchDimensionModal from './BatchDimensionModal.vue'
import BatchNoiseModal from './BatchNoiseModal.vue'
import BatchTagsModal from './BatchTagsModal.vue'
import TagCategoryModal from './TagCategoryModal.vue'
import TagEditModal from './TagEditModal.vue'
import TaskTypeModal from '../../../views/TasksLogic/TaskTypeModal.vue'
import TaskDetailModal from '../../../views/TasksLogic/TaskDetailModal.vue'
import TestCaseDetailModal from './TestCaseDetailModal.vue'
import AudioPlayerModal from '../AudioPlayerModal.vue'
import AudioSelectModal from '../AudioSelectModal.vue'
import ReevaluateSelectModal from './ReevaluateSelectModal.vue'

defineProps({
  includeStyles: { type: Boolean, default: true }
})

// 使用局部定义的ModalManager类型，避免与shared/types/index.ts中的定义冲突
const manager = getModalManager()

const confirmedEvents = new Map<string, { timestamp: number, data: any }>()

const addDeviceModalCreationLock = (() => {
  let locked = false
  let modalId = ''
  return {
    tryLock: (newModalId: string): boolean => {
      if (locked && modalId === newModalId) {
        console.log(`[GlobalModalContainer] ADDDevice modal ${newModalId} already being created, blocking duplicate`)
        return false
      }
      locked = true
      modalId = newModalId
      return true
    },
    unlock: () => {
      locked = false
      modalId = ''
    }
  }
})()

const modalExecutionState = new Map<string, {
  confirmed: boolean
  closed: boolean
  processing: boolean
}>()

const confirmHandlerCache = new Map<string, (data: any) => void>()

// GlobalModalContainer 不需要 confirm 处理逻辑，因为 useModal.ts 中的 ModalManager 使用 Promise 模式
// 这里只需要处理模态框的关闭和状态管理
const getConfirmHandler = (modalId: string) => {
  if (confirmHandlerCache.has(modalId)) {
    const cached = confirmHandlerCache.get(modalId)!
    console.log(`[GlobalModalContainer] Using cached handler for modalId: ${modalId}`)
    return cached
  }
  
  modalExecutionState.set(modalId, { confirmed: false, closed: false, processing: false })
  
  const handler = ((data: any) => {
    const state = modalExecutionState.get(modalId)
    if (!state) {
      console.log(`[GlobalModalContainer] No execution state for ${modalId}, skipping`)
      return
    }
    
    if (state.processing || state.confirmed || state.closed) {
      console.log(`[GlobalModalContainer] Confirm SKIPPED for ${modalId}, processing: ${state.processing}, confirmed: ${state.confirmed}, closed: ${state.closed}`)
      return
    }
    
    state.processing = true
    console.log(`[GlobalModalContainer] handleConfirm EXECUTING for ${modalId}`, data)
    
    // useModal.ts 中的 ModalManager 不支持 confirm 方法，这里只更新状态
    setTimeout(() => {
      state.confirmed = true
      state.processing = false
      console.log(`[GlobalModalContainer] Modal ${modalId} processing finished, confirmed: true`)
    }, 100)
  })
  
  console.log(`[GlobalModalContainer] Creating NEW handler for modalId: ${modalId}`)
  confirmHandlerCache.set(modalId, handler)
  return handler
}

// 使用 useModal.ts 中的 ModalManager 的 getActiveModals() 方法获取激活的模态框列表
const activeModals = computed(() => {
  const modals = manager.getActiveModals()
  // 将 ModalInstance 数组转换为 [id, modal] 元组数组，适配模板中的 v-for
  console.log('[GlobalModalContainer] getActiveModals returned:', modals.length, 'modals')
  modals.forEach(modal => {
    console.log('[GlobalModalContainer] Modal:', modal.id, modal.type, 'props:', Object.keys(modal.props || {}))
  })
  return modals.map(modal => [modal.id, modal] as [string, any])
})

// 移除对不存在的 activeModals 属性的监听
// watch(
//   () => manager.activeModals,
//   (newVal, oldVal) => {
//     console.log(`[GlobalModalContainer] manager.activeModals changed:`,
//       `old: ${Object.keys(oldVal).length}`,
//       `new: ${Object.keys(newVal).length}`
//     )
//   },
//   { deep: true }
// )

const getModalComponent = (type: string) => {
  const componentMap: Record<string, any> = {
    [MODAL_TYPES.TEST_CASE_RELATED]: TestCaseModal,
    [MODAL_TYPES.TEST_GROUP]: TestCaseModal,
    [MODAL_TYPES.TEST_CASE_IMPORT]: TestCaseModal,
    [MODAL_TYPES.TEST_CASE_EXPORT]: TestCaseModal,
    [MODAL_TYPES.ADD_TEST_CASE]: AddTestCaseModal,
    [MODAL_TYPES.SCAN_DEVICES]: ScanDevicesModal,
    [MODAL_TYPES.BASIC_CONFIRM]: ModalConfirm,
    [MODAL_TYPES.DELETE_CONFIRM]: ModalConfirm,
    [MODAL_TYPES.API_OTHER_CONFIG]: APIEditModal,
    [MODAL_TYPES.DETAIL_VIEW]: DetailViewModal,
    [MODAL_TYPES.IMPORT_EXPORT]: ImportExportModal,
    [MODAL_TYPES.CRUD_FORM]: CRUDFormModal,
    [MODAL_TYPES.UPLOAD_AUDIO_IMPORT]: UploadFileModal,
    [MODAL_TYPES.URL_IMPORT]: URLImportModal,
    [MODAL_TYPES.FOLDER_IMPORT]: FolderImportModal,
    [MODAL_TYPES.TASK_RELATED]: TaskTypeModal,
    [MODAL_TYPES.TASK_DETAIL]: TaskDetailModal,
    [MODAL_TYPES.TEST_CASE_DETAIL]: TestCaseDetailModal,
    [MODAL_TYPES.SPL_CALIBRATION]: SPLCalibrationModal,
    [MODAL_TYPES.AUDIO_IMPORT]: UploadFileModal,
    [MODAL_TYPES.ADD_DEVICE]: CRUDFormModal,
    [MODAL_TYPES.EDIT_DEVICE]: CRUDFormModal,
    [MODAL_TYPES.ADD_MAPPING]: CRUDFormModal,
    [MODAL_TYPES.EDIT_MAPPING]: CRUDFormModal,
    [MODAL_TYPES.MAPPING_DETAILS]: DetailViewModal,
    [MODAL_TYPES.EDIT_METADATA]: CRUDFormModal,
    [MODAL_TYPES.GLOBAL_PLAYBACK_DEVICE]: GlobalPlaybackDeviceModal,
    [MODAL_TYPES.AUDIO_PLAYER]: AudioPlayerModal,
    [MODAL_TYPES.AUDIO_SELECT]: AudioSelectModal,
    [MODAL_TYPES.REEVALUATE]: ReevaluateSelectModal,
    [MODAL_TYPES.BATCH_ALGORITHM_PARAMS]: BatchAlgorithmParamsModal,
    [MODAL_TYPES.BATCH_SPL]: BatchSPLModal,
    [MODAL_TYPES.BATCH_PLAYBACK_DEVICE]: BatchPlaybackDeviceModal,
    [MODAL_TYPES.BATCH_ADJUST_GROUP]: BatchAdjustGroupModal,
    [MODAL_TYPES.BATCH_DIMENSION]: BatchDimensionModal,
    [MODAL_TYPES.BATCH_NOISE]: BatchNoiseModal,
    [MODAL_TYPES.BATCH_TAGS]: BatchTagsModal,
    [MODAL_TYPES.TAG_CATEGORY]: TagCategoryModal,
    [MODAL_TYPES.TAG_EDIT]: TagEditModal
  }
  return componentMap[type] || null
}

const handleClose = (modalId: string) => {
  console.log('[GlobalModalContainer] handleClose called, modalId:', modalId)
  if (modalExecutionState.has(modalId)) {
    const state = modalExecutionState.get(modalId)
    if (state) {
      state.closed = true
      state.processing = false
    }
  }

  // 使用 useModal.ts 中的 ModalManager 的 close 方法
  if (typeof manager.close === 'function') {
    console.log(`[GlobalModalContainer] Closing modal ${modalId}`)
    manager.close(modalId)
  }
}

const handleCancel = (modalId: string, reason: any) => {
  // useModal.ts 中的 ModalManager 不支持 cancel 方法，直接关闭
  handleClose(modalId)
}

const handleUpdateProps = (modalId: string, newProps: any) => {
  // 使用 useModal.ts 中的 ModalManager 的 updateModalProps 方法
  if (typeof manager.updateModalProps === 'function') {
    manager.updateModalProps(modalId, newProps)
  }
}

const handleConfigChange = (modalId: string, config: any) => {
  // 使用 updateModalProps 方法更新配置
  handleUpdateProps(modalId, { uploadConfig: config })
}

const handleSave = async (modalId: string, data: any) => {
  console.log('[GlobalModalContainer] handleSave called with data:', JSON.stringify(data, null, 2));
  
  if (data?.mode === 'export' && data?.data) {
    try {
      const exportData = data.data;
      console.log('[GlobalModalContainer] exportData:', JSON.stringify(exportData, null, 2));
      
      const ids = exportData.ids || [];
      const format = exportData.format === 'xlsx' ? 'xlsx' : 'json';
      const includeDeleted = exportData.includeDeleted || false;
      
      console.log('[GlobalModalContainer] 导出参数:', { ids: ids.length, format, includeDeleted });
      
      if (ids.length === 0) {
        alert('没有可导出的用例');
        handleClose(modalId);
        return;
      }
      
      const response = await testcasesApi.export(ids, format, includeDeleted);
      
      console.log('[GlobalModalContainer] 导出响应类型:', typeof response);
      console.log('[GlobalModalContainer] 导出响应是否为Blob:', response instanceof Blob);
      console.log('[GlobalModalContainer] 导出响应大小:', response instanceof Blob ? response.size : 'N/A');
      
      if (response instanceof Blob) {
        const url = URL.createObjectURL(response);
        const a = document.createElement('a');
        a.href = url;
        
        const extension = format;
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        a.download = `testcases_export_${timestamp}.${extension}`;
        
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('[GlobalModalContainer] 导出成功');
      } else {
        console.log('[GlobalModalContainer] 导出响应:', response);
      }
    } catch (error) {
      console.error('[GlobalModalContainer] 导出失败:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误'
      alert('导出失败: ' + errorMessage);
    }
  }
  
  handleClose(modalId)
}

const handleSelectFolder = (modalId: string, data: any) => {
  // useModal.ts 中的 ModalManager 不支持 confirm 方法
  // 这里只需要关闭模态框，Promise 解析由 useModal 内部处理
  handleClose(modalId)
}
</script>

<style scoped>
.modal-container-wrapper {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: var(--z-index-modal-top);
  pointer-events: none;
}

/* 只有当有active模态框时才允许指针事件 */
.modal-container-wrapper:has(.modal-overlay) {
  pointer-events: auto;
}

.modal-enter-active,
.modal-leave-active {
  transition: all 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-error {
  padding: 20px;
  text-align: center;
  color: #ef4444;
}

.modal-error p {
  margin: 0 0 8px 0;
}

.error-details {
  font-size: 12px;
  color: #9ca3af;
}
</style>
