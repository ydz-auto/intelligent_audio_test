<template>
  <div class="input-confirm-modal">
    <div class="modal-body">
      <label class="input-label">
        {{ label }}
        <span v-if="required" class="required">*</span>
      </label>
      <input
        ref="inputRef"
        v-model="value"
        type="text"
        class="form-input"
        :placeholder="placeholder"
        @keydown.enter="handleConfirm"
      />
      <p v-if="hint" class="form-hint">{{ hint }}</p>
      <p v-if="validationError" class="form-error">{{ validationError }}</p>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="emit('cancel')">
        {{ cancelText }}
      </button>
      <button
        type="button"
        class="btn"
        :class="danger ? 'btn-danger' : 'btn-primary'"
        :disabled="confirmDisabled"
        @click="handleConfirm"
      >
        {{ confirmText }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'

/**
 * INT-286：单字段表单输入确认模态（INPUT_CONFIRM）。
 *
 * 替代业务侧 window.prompt 收集输入：可样式化、可校验（required + 自定义
 * validate）、危险操作确认按钮可标红（danger）。确认载荷 { value }（已 trim）。
 */
import { computed, onMounted, ref } from 'vue'

interface Props {
  modalId: string
  title?: string
  label: string
  placeholder?: string
  initialValue?: string
  hint?: string
  /** 是否非空必填（默认 true） */
  required?: boolean
  confirmText?: string
  cancelText?: string
  /** 危险操作 → 确认按钮标红（如卸载应用） */
  danger?: boolean
  /** 自定义校验：返回错误文案，null 表示通过 */
  validate?: (value: string) => string | null
}

interface Emits {
  (e: 'confirm', data: { value: string }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '输入',
  placeholder: '',
  initialValue: '',
  hint: '',
  required: true,
  confirmText: '确定',
  cancelText: '取消',
  danger: false,
  validate: undefined,
})

const emit = defineEmits<Emits>()

const value = ref(props.initialValue)
const inputRef = ref<HTMLInputElement | null>(null)

const trimmed = computed(() => value.value.trim())

const validationError = computed(() => {
  if (!props.validate) return null
  return props.validate(trimmed.value)
})

const confirmDisabled = computed(() => {
  if (props.required && !trimmed.value) return true
  return validationError.value != null
})

function handleConfirm() {
  if (confirmDisabled.value) return
  emit('confirm', { value: trimmed.value })
}

onMounted(() => {
  inputRef.value?.focus()
})
</script>

<style scoped>
.modal-body {
  padding: 20px 24px 4px;
}
.input-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}
.required {
  color: var(--destructive);
}
.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--radius-control);
  font-size: 14px;
  box-sizing: border-box;
}
.form-input:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--secondary) 10%, transparent);
}
.form-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-gray-400);
}
.form-error {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--destructive);
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
  padding: 16px 24px;
}
.btn {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-control);
  font-size: 14px;
  cursor: pointer;
}
.btn-secondary {
  background: var(--muted);
  color: var(--foreground);
}
.btn-primary {
  background: var(--secondary);
  color: var(--background);
}
.btn-danger {
  background: var(--destructive);
  color: white;
}
.btn:disabled {
  background: var(--color-gray-300);
  cursor: not-allowed;
}
</style>
