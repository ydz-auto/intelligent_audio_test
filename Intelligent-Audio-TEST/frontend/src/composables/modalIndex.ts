// 基础模态窗组件
export { default as BasicModal } from '../components/common/modal/BasicModal.vue'

// 全局模态窗容器
export { default as GlobalModalContainer } from '../components/common/modal/GlobalModalContainer.vue'

// 通知组件
export { default as Notification } from '../components/common/modal/Notification.vue'

// 具体功能模态窗组件
export { default as APIEditModal } from '../components/common/modal/APIEditModal.vue'
export { default as AudioPreviewModal } from '../components/common/modal/AudioPreviewModal.vue'
export { default as CRUDFormModal } from '../components/common/modal/CRUDFormModal.vue'
export { default as DetailViewModal } from '../components/common/modal/DetailViewModal.vue'
export { default as FolderImportModal } from '../components/common/modal/FolderImportModal.vue'
export { default as GlobalPlaybackDeviceModal } from '../components/common/modal/GlobalPlaybackDeviceModal.vue'
export { default as SPLCalibrationModal } from '../components/common/modal/SPLCalibrationModal.vue'
export { default as ImportExportModal } from '../components/common/modal/ImportExportModal.vue'
export { default as ScanDevicesModal } from '../components/common/modal/ScanDevicesModal.vue'
export { default as TestCaseDetailModal } from '../components/common/modal/TestCaseDetailModal.vue'
export { default as URLImportModal } from '../components/common/modal/URLImportModal.vue'
export { default as UploadFileModal } from '../components/common/modal/UploadFileModal.vue'
export { default as modalConfirm } from '../components/common/modal/ModalConfirm.vue'

// 模态框工具函数和常量
export {
  useModal,
  useModalControl,
  MODAL_MANAGER_KEY,
  getModalManager,
  provideModal,
  MODAL_TYPES
} from './useModal'

export type { 
  ModalType,
  ModalConfig,
  ActiveModal
} from '../shared/types'

export type { ModalManager } from './useModal'
