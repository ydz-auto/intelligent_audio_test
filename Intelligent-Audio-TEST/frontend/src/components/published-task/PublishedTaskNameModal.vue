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
   （test-case-manager.css，仅 .active 才可见）串扰；transform: none 对齐全局 .modal 位移 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 13000;
  overflow: hidden;
  opacity: 1;
  visibility: visible;
}

.modal {
  background-color: #fff;
  border-radius: var(--border-radius-xl);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
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
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #343a40;
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #6c757d;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--border-radius-full);
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
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
  border-top: 1px solid #e9ecef;
  background-color: #f8f9fa;
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
  background-color: var(--primary-color, #ff6a00);
  color: #fff;
}

.btn-primary:hover {
  opacity: 0.88;
}

.btn-primary:disabled {
  background-color: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--background-secondary, #f0f0f0);
  color: #333;
}

.btn-secondary:hover {
  background-color: #e0e0e0;
}

.form-group {
  margin-bottom: 0;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}

.required {
  color: #e53e3e;
}

.form-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: var(--border-radius-md);
  font-size: 13px;
  background: #fff;
  color: #1f2937;
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary-color, #ff6a00);
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.15);
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
}
</style>
