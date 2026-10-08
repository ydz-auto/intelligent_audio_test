<template>
  <teleport to="body">
    <div class="modal-overlay" v-if="visible" style="opacity: 1 !important; visibility: visible !important; pointer-events: auto !important;">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>音频试听配置</h3>
          <button type="button" class="modal-close" @click="handleClose">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-section">
            <h4>选择播放模式 <span class="required">*</span></h4>
            <div class="radio-group">
              <label class="radio-item">
                <input type="radio" value="frontend" v-model="previewConfig.playbackMode">
                <span>浏览器播放</span>
              </label>
              <label class="radio-item">
                <input type="radio" value="backend" v-model="previewConfig.playbackMode">
                <span>实验室播放</span>
              </label>
            </div>
            <p class="mode-description" v-if="previewConfig.playbackMode === 'frontend'">
              <i class="fas fa-info-circle"></i> 音频将通过浏览器前端直接播放
            </p>
            <p class="mode-description" v-else>
              <i class="fas fa-info-circle"></i> 音频将通过用例配置中的播放设备在实验室播放
            </p>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="handleClose">取消</button>
          <button type="button" class="btn btn-primary" @click="handlePreview">
            <i class="fas fa-play"></i> 开始试听
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue';
import { audiosPort } from '../../../composables/audio/audiosPort';

const props = defineProps({
  visible: { type: Boolean, default: false },
  audioId: { type: String, required: false, default: null },
  audioType: { type: String, default: 'dry' },
  playbackDevices: { type: Array, default: () => [] },
  initialSelectedDevices: { type: Array, default: () => [] },
  initialSpl: { type: Number, default: 65 },
  initialOffset: { type: Number, default: 0 }
});

const emit = defineEmits(['close', 'preview']);

const previewConfig = ref({
  playbackMode: 'frontend'
});

watch(() => props.visible, (newValue) => {
  if (newValue) {
    previewConfig.value.playbackMode = 'frontend';
  }
});

const handleClose = () => {
  emit('close');
};

const handleKeyDown = (event) => {
  if (event.key === 'Escape' && props.visible) {
    handleClose();
  }
};

watch(() => props.visible, (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown);
  } else {
    window.removeEventListener('keydown', handleKeyDown);
  }
}, { immediate: true });

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

const handlePreview = () => {
  const result = {
    audioId: props.audioId,
    playbackMode: previewConfig.value.playbackMode
  };
  emit('preview', result);
  handleClose();
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: color-mix(in srgb, var(--color-black) 50%, transparent);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: calc(var(--z-index-modal-top, 13000) + 2);
  animation: fadeIn 0.3s ease;
  opacity: 1 !important;
  visibility: visible !important;
  pointer-events: auto !important;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px color-mix(in srgb, var(--color-black) 15%, transparent);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { transform: translateY(-20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--muted);
  background: linear-gradient(135deg, var(--muted) 0%, var(--muted) 100%);
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
}

.form-section {
  margin-bottom: 24px;
  padding: 20px;
  background-color: var(--muted);
  border-radius: 8px;
  border: 1px solid var(--muted);
}

.form-section h4 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--foreground);
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: var(--muted-foreground);
}

.required {
  color: var(--destructive);
  font-weight: bold;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 0.2rem color-mix(in srgb, var(--secondary) 25%, transparent);
}

.form-control:invalid {
  border-color: var(--destructive);
  box-shadow: 0 0 0 0.2rem color-mix(in srgb, var(--destructive) 25%, transparent);
}

.scan-status {
  margin-bottom: 20px;
  padding: 12px;
  border-radius: 6px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.scan-status-scanning {
  background-color: var(--color-secondary-light);
  color: var(--secondary);
  border: 1px solid var(--secondary-light);
}

.scan-status-error {
  background-color: var(--destructive-light);
  color: var(--color-red-700);
  border: 1px solid var(--destructive-light);
}

.device-group {
  margin-bottom: 20px;
  padding: 16px;
  background-color: var(--color-white);
  border: 1px solid var(--muted);
  border-radius: 6px;
}

.device-group h5 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
  color: var(--muted-foreground);
}

.checkbox-group {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 12px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background-color: var(--muted);
  border: 1px solid var(--muted);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.checkbox-item:hover {
  background-color: var(--color-secondary-light);
  border-color: var(--secondary-light);
}

.checkbox-item input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.checkbox-item span {
  margin: 0;
  cursor: pointer;
  font-weight: 400;
  word-break: break-word;
}

.radio-group {
  display: flex;
  gap: 24px;
  margin-top: 8px;
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.radio-item input[type="radio"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.radio-item label {
  margin: 0;
  cursor: pointer;
  font-weight: 400;
}

.mode-description {
  margin-top: 12px;
  padding: 12px;
  background-color: var(--color-secondary-light);
  border: 1px solid var(--secondary-light);
  border-radius: 6px;
  font-size: 14px;
  color: var(--secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-description i {
  font-size: 16px;
}

.modal-footer {
  padding: 20px 24px;
  border-top: 1px solid var(--muted);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn {
  padding: 10px 24px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn-primary:hover:not(:disabled) {
  background-color: var(--secondary-deep);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--secondary) 30%, transparent);
}

.btn-primary:disabled {
  background-color: var(--muted-foreground);
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.btn-secondary {
  background-color: var(--muted);
  color: var(--muted-foreground);
  border: 1px solid var(--border);
}

.btn-secondary:hover {
  background-color: var(--muted);
  color: var(--muted-foreground);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-black) 10%, transparent);
}
</style>
