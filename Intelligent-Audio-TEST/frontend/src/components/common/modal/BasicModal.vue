<template>
  <Teleport to="body">
    <div
      class="modal-overlay"
      :class="{ active: visible }"
      :style="overlayStyle"
      @click="handleMaskClick($event)"
      v-if="visible"
    >
      <div
        class="modal"
        :style="modalStyle"
        ref="modalContentRef"
        @click.stop
      >
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button
            v-if="closable"
            type="button"
            class="modal-close"
            @click="handleClose"
          >
            <i class="fas fa-times"></i>
          </button>
        </div>
        
        <!-- 滚动内容区域 -->
        <div class="modal-scroll-container">
          <div class="modal-body">
            <slot></slot>
          </div>
          
          <div class="modal-footer" v-if="showFooter">
            <slot name="footer">
              <button
                v-if="showCancelBtn"
                type="button"
                class="btn btn-secondary"
                @click="handleCancel"
              >
                {{ cancelText }}
              </button>
              <button
                v-if="showConfirmBtn"
                type="button"
                class="btn btn-primary"
                :disabled="confirmLoading"
                @click="handleConfirm"
              >
                <span v-if="confirmLoading" class="loading-spinner"></span>
                {{ confirmText }}
              </button>
            </slot>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch, ref } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '模态窗' },
  modalId: { type: String, default: '' },

  width: { type: String, default: '500px' },
  maxWidth: { type: String, default: '90vw' },
  maxHeight: { type: String, default: '90vh' },

  closable: { type: Boolean, default: true },
  maskClosable: { type: Boolean, default: false },

  showFooter: { type: Boolean, default: true },
  showConfirmBtn: { type: Boolean, default: true },
  showCancelBtn: { type: Boolean, default: true },
  confirmText: { type: String, default: '确认' },
  cancelText: { type: String, default: '取消' },
  confirmLoading: { type: Boolean, default: false },
  zIndexOffset: { type: Number, default: 0 }
})

const overlayStyle = computed(() => {
  const baseZIndex = 13000
  const offset = props.zIndexOffset * 100
  return { zIndex: baseZIndex + offset }
})

const emit = defineEmits(['close', 'confirm', 'cancel', 'update:visible'])

const modalStyle = computed(() => {
  return { width: props.width, maxWidth: props.maxWidth, maxHeight: props.maxHeight }
})

const modalContentRef = ref<HTMLElement | null>(null)

const handleClose = () => {
  console.log('[BasicModal] handleClose called, modal:', props.modalId)
  emit('close')
  emit('update:visible', false)
}

const handleMaskClick = (event: MouseEvent) => {
  if (props.maskClosable && event.target === event.currentTarget) {
    handleClose()
  }
}

const handleConfirm = () => {
  emit('confirm')
}

const handleCancel = () => {
  emit('cancel')
  emit('update:visible', false)
}

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.visible) {
    handleClose()
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown)
  } else {
    window.removeEventListener('keydown', handleKeyDown)
  }
}, { immediate: true })

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: color-mix(in srgb, var(--color-black) 50%, transparent);
  display: flex;
  justify-content: center;
  align-items: center;
  transition: opacity 0.3s ease, visibility 0.3s ease;
  overflow: hidden;
}

.modal {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px color-mix(in srgb, var(--color-black) 15%, transparent);
  max-height: 90vh;
  overflow: hidden;
  transition: transform 0.3s ease, opacity 0.3s ease;
}

/* 滚动容器，将滚动条限制在内容区域 */
.modal-scroll-container {
  max-height: calc(90vh - 70px);
  overflow-y: auto;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  position: relative;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--muted);
  background: linear-gradient(135deg, var(--muted) 0%, var(--muted) 100%);
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--foreground);
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--muted-foreground);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: var(--foreground);
  background-color: var(--muted);
  transform: rotate(90deg);
}

.modal-body {
  padding: 24px;
  background-color: white;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid var(--muted);
  background-color: var(--muted);
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
  /* 确保底部固定在模态窗底部 */
  position: sticky;
  bottom: 0;
  z-index: 100;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary:hover {
  background-color: var(--secondary);
}

.btn-primary:disabled {
  background-color: var(--border);
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--gray-light);
  color: var(--foreground);
}

.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid color-mix(in srgb, var(--color-white) 30%, transparent);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 1s ease-in-out infinite;
  margin-right: 8px;
  vertical-align: middle;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
