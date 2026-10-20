<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal published-task-name-modal">
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button class="modal-close" @click="handleClose"><i class="fas fa-times"></i></button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">{{ label }} <span class="required" v-if="required">*</span></label>
            <input
              ref="inputRef"
              v-model="name"
              class="form-input"
              :placeholder="placeholder"
              maxlength="255"
              :disabled="submitting"
              @keyup.enter="handleConfirm"
            />
            <div class="form-hint" v-if="hint">{{ hint }}</div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleClose">取消</button>
          <button class="btn btn-primary" :disabled="!canSubmit || submitting" @click="handleConfirm">
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { ref, computed, onMounted, nextTick } from 'vue';

const props = withDefaults(defineProps<{
  title: string;
  label: string;
  placeholder?: string;
  hint?: string;
  initialValue?: string;
  required?: boolean;
  confirmText?: string;
  submitting?: boolean;
}>(), {
  placeholder: '',
  hint: '',
  initialValue: '',
  required: true,
  confirmText: '确定',
  submitting: false,
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'confirm', payload: { name: string }): void;
}>();

const name = ref(props.initialValue);
const inputRef = ref<HTMLInputElement | null>(null);

const canSubmit = computed(() =>
  (!props.required || name.value.trim().length > 0) && !props.submitting
);

function handleClose() {
  emit('close');
}

function handleConfirm() {
  if (!canSubmit.value) return;
  emit('confirm', { name: name.value.trim() });
}

onMounted(() => {
  nextTick(() => inputRef.value?.focus());
});
</script>

<style scoped>
/* opacity/visibility 显式声明，规避全局 .modal-overlay{visibility:hidden;opacity:0}
   （test-case-manager.css，仅 .active 才可见）串扰；transform: none 对齐全局 .modal 位移。
   INT-1081：颜色全部收敛为语义令牌（modal 域令牌 / --background / --primary 等），深浅两套自动换肤。 */
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
  z-index: 13000;
  overflow: hidden;
  opacity: 1;
  visibility: visible;
}

.modal {
  background-color: var(--background);
  border-radius: var(--border-radius-xl);
  box-shadow: 0 4px 20px color-mix(in srgb, var(--color-black) 15%, transparent);
  display: flex;
  flex-direction: column;
  transform: none;
}

.published-task-name-modal {
  width: 440px;
  max-width: 92vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--modal-border-color);
  background: linear-gradient(135deg, var(--modal-surface-top) 0%, var(--modal-border-color) 100%);
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--modal-title-color);
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--modal-muted);
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--border-radius-full);
  transition: all 0.2s;
}

.modal-close:hover {
  color: var(--modal-title-color);
  background-color: var(--modal-border-color);
}

.modal-body {
  padding: 20px 24px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-top: 1px solid var(--modal-border-color);
  background-color: var(--modal-surface-top);
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: var(--border-radius-md);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background-color: var(--primary);
  color: var(--color-white);
}

.btn-primary:hover {
  opacity: 0.88;
}

.btn-primary:disabled {
  background-color: var(--btn-primary-disabled-bg);
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--gray-light);
  color: var(--foreground);
}

.btn-secondary:hover {
  background-color: var(--btn-secondary-hover-bg);
}

.form-group {
  margin-bottom: 0;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--modal-text);
}

.required {
  color: var(--danger-required);
}

.form-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--border-radius-md);
  font-size: 13px;
  background: var(--background);
  color: var(--modal-text);
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 15%, transparent);
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-gray-400);
}
</style>
