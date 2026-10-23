<template>
  <Teleport to="body">
    <div 
      class="modal-container-wrapper"
      :class="{ 'modal-container-wrapper--active': activeModals.length > 0 }"
    >
      <template v-for="[modalId, modalItem, index] in activeModalsWithIndex" :key="modalId">
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
          :z-index-offset="index"
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
                if (isNativeEvent(data)) return;
                if (modalItem.props && typeof modalItem.props.onSave === 'function') {
                  try {
                    modalItem.props.onSave(data);
                  } catch (error) {
                    console.error('[GlobalModalContainer] onSave回调执行失败:', error);
                  }
                }
                modalItem.resolve(data);
                handleClose(modalId);
              }"
              @cancel="(data: any) => {
                if (isNativeEvent(data)) return;
                // INT-1011：取消收敛为 resolve(null)，不再 reject（避免 Uncaught (in promise)）
                modalItem.resolve(null);
                handleClose(modalId);
              }"
              @save="(data: any) => {
                if (isNativeEvent(data)) return;
                if (modalItem.props && typeof modalItem.props.onSave === 'function') {
                  try {
                    modalItem.props.onSave(data);
                  } catch (error) {
                    console.error('[GlobalModalContainer] onSave回调执行失败:', error);
                  }
                }
                modalItem.resolve(data);
                handleClose(modalId);
              }"
              @select="(data: any) => {
                if (isNativeEvent(data)) return;
                modalItem.resolve(data);
                handleClose(modalId);
              }"
              @selectMultiple="(data: any) => {
                if (isNativeEvent(data)) return;
                modalItem.resolve(data);
                handleClose(modalId);
              }"
              @uploadRequest="() => {
                handleClose(modalId);
                requestUploadAction('openUploadModal');
              }"
              @folderImportRequest="() => {
                handleClose(modalId);
                requestUploadAction('openFolderImport');
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
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { computed, watch } from 'vue'
import { getModalManager } from '../../../composables/modal/useModal'
import { useUploadState } from '../../../composables/upload/useUploadState'
import type { ActiveModal } from '../../../composables/modal/types'
import BasicModal from './BasicModal.vue'
import { testcasesPort } from '../../../composables/testCase/testcasesPort'
import { useNotification } from '@/composables/modal/useNotification'

const notification = useNotification()

const isNativeEvent = (data: any): boolean => {
  return data !== undefined && data !== null
    && typeof data === 'object'
    && data.target !== undefined
    && data.type !== undefined
    && typeof data.preventDefault === 'function'
}

defineProps({
  includeStyles: { type: Boolean, default: true }
})

// 使用局部定义的ModalManager类型，避免与shared/types/index.ts中的定义冲突
const manager = getModalManager()
const { requestAction: requestUploadAction } = useUploadState()

const confirmedEvents = new Map<string, { timestamp: number, data: any }>()

const addDeviceModalCreationLock = (() => {
  let locked = false
  let modalId = ''
  return {
    tryLock: (newModalId: string): boolean => {
      if (locked && modalId === newModalId) {
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
    return confirmHandlerCache.get(modalId)!
  }

  modalExecutionState.set(modalId, { confirmed: false, closed: false, processing: false })

  const handler = ((data: any) => {
    const state = modalExecutionState.get(modalId)
    if (!state) {
      return
    }

    if (state.processing || state.confirmed || state.closed) {
      return
    }

    state.processing = true

    // useModal.ts 中的 ModalManager 不支持 confirm 方法，这里只更新状态
    setTimeout(() => {
      state.confirmed = true
      state.processing = false
    }, 100)
  })

  confirmHandlerCache.set(modalId, handler)
  return handler
}

// 使用 useModal.ts 中的 ModalManager 的 getActiveModals() 方法获取激活的模态框列表
const activeModals = computed(() => {
  const modals = manager.getActiveModals()
  // 将 ModalInstance 数组转换为 [id, modal] 元组数组，适配模板中的 v-for
  return modals.map(modal => [modal.id, modal] as [string, any])
})

const activeModalsWithIndex = computed(() => {
  const modals = manager.getActiveModals()
  return modals.map((modal, index) => [modal.id, modal, index] as [string, any, number])
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

const handleClose = (modalId: string) => {
  if (modalExecutionState.has(modalId)) {
    const state = modalExecutionState.get(modalId)
    if (state) {
      state.closed = true
      state.processing = false
    }
  }

  // 使用 useModal.ts 中的 ModalManager 的 close 方法
  if (typeof manager.close === 'function') {
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
  if (data?.mode === 'export' && data?.data) {
    try {
      const exportData = data.data;

      const ids = exportData.ids || [];
      const format = exportData.format === 'xlsx' ? 'xlsx' : 'json';
      const includeDeleted = exportData.includeDeleted || false;

      if (ids.length === 0) {
        notification.warning('没有可导出的用例');
        handleClose(modalId);
        return;
      }

      const response = await testcasesPort.export(ids, format, includeDeleted);

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
      }
    } catch (error) {
      console.error('[GlobalModalContainer] 导出失败:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误'
      notification.error('导出失败: ' + errorMessage);
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
  color: var(--color-red-500);
}

.modal-error p {
  margin: 0 0 8px 0;
}

.error-details {
  font-size: 12px;
  color: var(--color-gray-400);
}
</style>
