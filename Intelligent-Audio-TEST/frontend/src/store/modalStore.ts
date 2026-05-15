import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface DeleteResult {
  success: boolean;
  message: string;
  count: number;
  failedIds?: (string | number)[];
}

export const useModalStore = defineStore('modal', () => {
  const STORAGE_KEY = 'modal-store'

  const loadFromStorage = (): Record<string, any> => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        return JSON.parse(stored)
      }
    } catch (e) {
      console.warn('[ModalStore] Failed to load from storage:', e)
    }
    return {}
  }

  const saveToStorage = (data: Record<string, any>) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (e) {
      console.warn('[ModalStore] Failed to save to storage:', e)
    }
  }

  const savedState = loadFromStorage()

  const showModal = ref<boolean>(savedState.showModal ?? false)
  const showDetailsModal = ref<boolean>(savedState.showDetailsModal ?? false)
  const showCalibrationModal = ref<boolean>(savedState.showCalibrationModal ?? false)

  const showUploadModal = ref<boolean>(savedState.showUploadModal ?? false)
  const showUrlImportModal = ref<boolean>(savedState.showUrlImportModal ?? false)
  const showConvertModal = ref<boolean>(savedState.showConvertModal ?? false)
  const showMetadataModal = ref<boolean>(savedState.showMetadataModal ?? false)

  const showAddDeviceModal = ref<boolean>(savedState.showAddDeviceModal ?? false)
  const showScanDevicesModal = ref<boolean>(savedState.showScanDevicesModal ?? false)

  const showAddModal = ref<boolean>(savedState.showAddModal ?? false)
  const showEditModal = ref<boolean>(savedState.showEditModal ?? false)
  const showAPIHealthModal = ref<boolean>(savedState.showAPIHealthModal ?? false)
  const showAPISettingsModal = ref<boolean>(savedState.showAPISettingsModal ?? false)
  const showRuleEditorModal = ref<boolean>(savedState.showRuleEditorModal ?? false)
  const showImportModal = ref<boolean>(savedState.showImportModal ?? false)
  const showAddCategoryModal = ref<boolean>(savedState.showAddCategoryModal ?? false)
  const showEditCategoryModal = ref<boolean>(savedState.showEditCategoryModal ?? false)
  const showDeleteResultModal = ref<boolean>(savedState.showDeleteResultModal ?? false)
  const deleteResult = ref<DeleteResult>({
    success: false,
    message: '',
    count: 0
  })

  const autoSave = ref<boolean>(true)

  const drafts = ref<Record<string, any>>({})

  const setDraft = (id: string, data: any) => {
    if (!id) return
    drafts.value[id] = JSON.parse(JSON.stringify(data))
  }

  const getDraft = (id: string): any | null => {
    if (!id || !drafts.value[id]) return null
    return JSON.parse(JSON.stringify(drafts.value[id]))
  }

  const clearDraft = (id: string) => {
    if (!id) return
    delete drafts.value[id]
  }

  const clearAllDrafts = () => {
    drafts.value = {}
  }

  const openAddMappingModal = () => {
    showModal.value = true
    showDetailsModal.value = false
    showCalibrationModal.value = false
  }

  const closeAddMappingModal = () => {
    showModal.value = false
  }

  const openDetailsModal = (_mappingId: string | number | null = null) => {
    showDetailsModal.value = true
    showModal.value = false
    showCalibrationModal.value = false
  }

  const closeDetailsModal = () => {
    showDetailsModal.value = false
  }

  const openCalibrationModal = (_mapping: any = null) => {
    showCalibrationModal.value = true
    showModal.value = false
    showDetailsModal.value = false
  }

  const closeCalibrationModal = () => {
    showCalibrationModal.value = false
  }

  const openUploadModal = () => {
    showUploadModal.value = true
  }

  const closeUploadModal = () => {
    showUploadModal.value = false
  }

  const openUrlImportModal = () => {
    showUrlImportModal.value = true
  }

  const closeUrlImportModal = () => {
    showUrlImportModal.value = false
  }

  const openConvertModal = () => {
    showConvertModal.value = true
  }

  const closeConvertModal = () => {
    showConvertModal.value = false
  }

  const openMetadataModal = () => {
    showMetadataModal.value = true
  }

  const closeMetadataModal = () => {
    showMetadataModal.value = false
  }

  const openAddDeviceModal = () => {
    showAddDeviceModal.value = true
    showScanDevicesModal.value = false
  }

  const closeAddDeviceModal = () => {
    showAddDeviceModal.value = false
  }

  const openScanDevicesModal = () => {
    showScanDevicesModal.value = true
    showAddDeviceModal.value = false
  }

  const closeScanDevicesModal = () => {
    showScanDevicesModal.value = false
  }

  const openAddModal = () => {
    showAddModal.value = true
  }

  const closeAddModal = () => {
    showAddModal.value = false
  }

  const openEditModal = () => {
    showEditModal.value = true
  }

  const closeEditModal = () => {
    showEditModal.value = false
  }

  const openAPIHealthModal = () => {
    showAPIHealthModal.value = true
  }

  const closeAPIHealthModal = () => {
    showAPIHealthModal.value = false
  }

  const openAPISettingsModal = () => {
    showAPISettingsModal.value = true
  }

  const closeAPISettingsModal = () => {
    showAPISettingsModal.value = false
  }

  const openRuleEditorModal = () => {
    showRuleEditorModal.value = true
  }

  const closeRuleEditorModal = () => {
    showRuleEditorModal.value = false
  }

  const openImportModal = () => {
    showImportModal.value = true
  }

  const closeImportModal = () => {
    showImportModal.value = false
  }

  const openAddCategoryModal = () => {
    showAddCategoryModal.value = true
  }

  const closeAddCategoryModal = () => {
    showAddCategoryModal.value = false
  }

  const openEditCategoryModal = () => {
    showEditCategoryModal.value = true
  }

  const closeEditCategoryModal = () => {
    showEditCategoryModal.value = false
  }

  const openDeleteResultModal = (result: Partial<DeleteResult>) => {
    deleteResult.value = { success: result.success ?? false, message: result.message ?? '', count: result.count ?? 0 }
    showDeleteResultModal.value = true
  }

  const closeDeleteResultModal = () => {
    showDeleteResultModal.value = false
  }

  const closeAllModals = () => {
    showModal.value = false
    showDetailsModal.value = false
    showCalibrationModal.value = false
    showUploadModal.value = false
    showUrlImportModal.value = false
    showConvertModal.value = false
    showMetadataModal.value = false
    showAddDeviceModal.value = false
    showScanDevicesModal.value = false
    showAddModal.value = false
    showEditModal.value = false
    showAPIHealthModal.value = false
    showAPISettingsModal.value = false
    showRuleEditorModal.value = false
    showImportModal.value = false
    showAddCategoryModal.value = false
    showEditCategoryModal.value = false
    showDeleteResultModal.value = false
  }

  const getModalState = (modalName: string) => {
    const stateMap: Record<string, any> = {
      'showModal': showModal,
      'showDetailsModal': showDetailsModal,
      'showCalibrationModal': showCalibrationModal,
      'showUploadModal': showUploadModal,
      'showUrlImportModal': showUrlImportModal,
      'showConvertModal': showConvertModal,
      'showMetadataModal': showMetadataModal,
      'showAddDeviceModal': showAddDeviceModal,
      'showScanDevicesModal': showScanDevicesModal,
      'showAddModal': showAddModal,
      'showEditModal': showEditModal,
      'showAPIHealthModal': showAPIHealthModal,
      'showAPISettingsModal': showAPISettingsModal,
      'showRuleEditorModal': showRuleEditorModal,
      'showImportModal': showImportModal,
      'showAddCategoryModal': showAddCategoryModal,
      'showEditCategoryModal': showEditCategoryModal,
      'showDeleteResultModal': showDeleteResultModal
    }
    return stateMap[modalName] || null
  }

  const toggleModal = (modalName: string) => {
    const modalRef = getModalState(modalName)
    if (modalRef) {
      modalRef.value = !modalRef.value
    }
  }

  const resetState = () => {
    closeAllModals()
  }

  return {
    showModal,
    showDetailsModal,
    showCalibrationModal,
    showUploadModal,
    showUrlImportModal,
    showConvertModal,
    showMetadataModal,
    showAddDeviceModal,
    showScanDevicesModal,
    showAddModal,
    showEditModal,
    showAPIHealthModal,
    showAPISettingsModal,
    showRuleEditorModal,
    showImportModal,
    showAddCategoryModal,
    showEditCategoryModal,
    showDeleteResultModal,
    deleteResult,
    autoSave,
    openAddMappingModal,
    closeAddMappingModal,
    openDetailsModal,
    closeDetailsModal,
    openCalibrationModal,
    closeCalibrationModal,
    openUploadModal,
    closeUploadModal,
    openUrlImportModal,
    closeUrlImportModal,
    openConvertModal,
    closeConvertModal,
    openMetadataModal,
    closeMetadataModal,
    openAddDeviceModal,
    closeAddDeviceModal,
    openScanDevicesModal,
    closeScanDevicesModal,
    openAddModal,
    closeAddModal,
    openEditModal,
    closeEditModal,
    openAPIHealthModal,
    closeAPIHealthModal,
    openAPISettingsModal,
    closeAPISettingsModal,
    openRuleEditorModal,
    closeRuleEditorModal,
    openImportModal,
    closeImportModal,
    openAddCategoryModal,
    closeAddCategoryModal,
    openEditCategoryModal,
    closeEditCategoryModal,
    openDeleteResultModal,
    closeDeleteResultModal,
    closeAllModals,
    getModalState,
    toggleModal,
    resetState,
    drafts,
    setDraft,
    getDraft,
    clearDraft,
    clearAllDrafts
  }
})
