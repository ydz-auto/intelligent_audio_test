<template>
  <div class="modal-confirm">
    <div class="modal-confirmContent">
      <div class="modal-confirmIcon" :class="{ 'modal-confirmIcon--success': isSuccess, 'modal-confirmIcon--danger': isDanger }">
        <i :class="isSuccess ? 'fas fa-check-circle' : (isDanger ? 'fas fa-exclamation-triangle' : 'fas fa-question-circle')"></i>
      </div>
      <p class="modal-confirmMessage">{{ content }}</p>
      <label v-if="checkboxLabel" class="modal-confirmCheckbox">
        <input type="checkbox" v-model="checkboxValue">
        {{ checkboxLabel }}
      </label>
    </div>
    <div class="modal-confirmActions">
      <button
        class="btn btn-secondary"
        @click="handleCancel"
      >
        {{ cancelText }}
      </button>
      <button
        class="btn"
        :class="isDanger ? 'btn-danger' : 'btn-primary'"
        @click="handleConfirm"
      >
        {{ confirmText }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useModalControl } from '../../../composables/useModal'

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    default: '确认操作'
  },
  content: {
    type: String,
    default: '确定要执行此操作吗？'
  },
  confirmText: {
    type: String,
    default: '确定'
  },
  cancelText: {
    type: String,
    default: '取消'
  },
  danger: {
    type: Boolean,
    default: false
  },
  checkboxLabel: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'confirm', 'cancel'])

const modalManager = useModalControl()

const checkboxValue = ref(false)

const isSuccess = computed(() => {
  return props.title?.includes('成功') || props.title?.toLowerCase().includes('success')
})

const isDanger = computed(() => {
  return props.danger || props.title?.includes('错误') || props.title?.includes('失败') || props.title?.toLowerCase().includes('error') || props.title?.toLowerCase().includes('failed')
})

const handleConfirm = () => {
  emit('confirm', { confirmed: true, checkboxValue: checkboxValue.value })
}

const handleCancel = () => {
  emit('cancel', { confirmed: false })
}
</script>

<style scoped>
.modal-confirm {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.modal-confirmContent {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.modal-confirmIcon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background-color: #e0f2fe;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #0284c7;
}

.modal-confirmIcon--success {
  background-color: #dcfce7;
  color: #16a34a;
}

.modal-confirmIcon--danger {
  background-color: #fef2f2;
  color: #dc2626;
}

.modal-confirmMessage {
  margin: 0;
  font-size: 15px;
  color: #475569;
  line-height: 1.6;
}

.modal-confirmCheckbox {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #475569;
  cursor: pointer;
  user-select: none;
}

.modal-confirmCheckbox input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.modal-confirmActions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
