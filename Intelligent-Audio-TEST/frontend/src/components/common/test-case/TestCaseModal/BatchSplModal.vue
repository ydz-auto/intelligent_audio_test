<template>
  <teleport to="body">
    <div class="modal-overlay" v-if="visible" @click="handleMaskClick">
      <div class="modal-container batch-spl-modal" @click.stop>
        <div class="modal-header">
          <h3>批量设置声压</h3>
          <button type="button" class="modal-close" @click="handleClose">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="batchSplInput">声压级 (dB)</label>
            <div class="spl-input-wrapper">
              <input
                type="number"
                id="batchSplInput"
                v-model.number="localSplValue"
                class="form-control"
                min="0"
                max="120"
                placeholder="请输入0-120之间的声压级"
              >
              <span class="spl-unit">dB</span>
            </div>
            <div class="spl-hint">
              <i class="fas fa-info-circle"></i>
              建议范围：60-85 dB，过高可能导致设备损坏
            </div>
          </div>
          <div class="spl-quick-select">
            <span class="quick-label">快速选择：</span>
            <button
              v-for="preset in splPresets"
              :key="preset.value"
              type="button"
              class="btn btn-quick"
              :class="{ active: localSplValue === preset.value }"
              @click="localSplValue = preset.value"
            >
              {{ preset.label }}
            </button>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="handleClose">取消</button>
          <button type="button" class="btn btn-primary" @click="handleConfirm">
            <i class="fas fa-check"></i> 确认
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

const props = defineProps<{
  visible: boolean;
  modelValue: number;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'update:modelValue', value: number): void;
  (e: 'confirm', value: number): void;
}>();

const localSplValue = ref(65);

const splPresets = [
  { label: '60 dB', value: 60 },
  { label: '65 dB', value: 65 },
  { label: '70 dB', value: 70 },
  { label: '75 dB', value: 75 },
  { label: '80 dB', value: 80 },
];

watch(() => props.modelValue, (newVal) => {
  localSplValue.value = newVal;
}, { immediate: true });

watch(() => props.visible, (newVal) => {
  console.log('[DEBUG] BatchSplModal visible changed to:', newVal, 'modelValue:', props.modelValue);
  if (newVal) {
    localSplValue.value = props.modelValue;
  }
});

function handleMaskClick(event: MouseEvent) {
  if (event.target === event.currentTarget) {
    handleClose();
  }
}

function handleClose() {
  emit('update:visible', false);
}

function handleConfirm() {
  if (localSplValue.value < 0 || localSplValue.value > 120) {
    return;
  }
  emit('update:modelValue', localSplValue.value);
  emit('confirm', localSplValue.value);
  handleClose();
}
</script>

<style>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 14001;
}

.modal-container {
  background-color: white;
  border-radius: var(--border-radius-xl);
  box-shadow: var(--shadow-lg);
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  font-size: 20px;
  color: var(--text-secondary);
  cursor: pointer;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  background-color: var(--background-secondary);
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: var(--text-primary);
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  font-size: 14px;
}

.btn {
  padding: 10px 20px;
  border-radius: var(--border-radius-md);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
  border: none;
}

.btn-primary:hover {
  background: var(--primary-hover);
}

.btn-secondary {
  background: var(--background-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  background: var(--background-tertiary);
}
</style>

<style scoped>
.batch-spl-modal {
  max-width: 420px;
}

.spl-input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spl-input-wrapper .form-control {
  flex: 1;
}

.spl-unit {
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
}

.spl-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.spl-hint i {
  color: var(--info-color);
}

.spl-quick-select {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.quick-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.btn-quick {
  padding: 6px 12px;
  font-size: 12px;
  border-radius: var(--border-radius-full);
  background: var(--secondary-light);
  color: var(--secondary-color);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-quick:hover {
  background: var(--secondary-color);
  color: white;
}

.btn-quick.active {
  background: var(--primary-color);
  color: white;
}
</style>
