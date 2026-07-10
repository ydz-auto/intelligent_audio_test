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
                <span>前端扬声器播放</span>
              </label>
              <label class="radio-item">
                <input type="radio" value="backend" v-model="previewConfig.playbackMode">
                <span>后端扬声器播放</span>
              </label>
            </div>
            <p class="mode-description" v-if="previewConfig.playbackMode === 'frontend'">
              <i class="fas fa-info-circle"></i> 音频将通过浏览器前端直接播放
            </p>
            <p class="mode-description" v-else>
              <i class="fas fa-info-circle"></i> 音频将通过用例配置中的播放设备在后端播放
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
import { audiosApi } from '../../../utils/api';

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
  background-color: rgba(0, 0, 0, 0.5);
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
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
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
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #343a40;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6c757d;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
  transform: rotate(90deg);
}

.modal-body {
  padding: 24px;
}

.form-section {
  margin-bottom: 24px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.form-section h4 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 600;
  color: #343a40;
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
  color: #495057;
}

.required {
  color: #dc3545;
  font-weight: bold;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.form-control:invalid {
  border-color: #dc3545;
  box-shadow: 0 0 0 0.2rem rgba(220, 53, 69, 0.25);
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
  background-color: #e3f2fd;
  color: #1976d2;
  border: 1px solid #bbdefb;
}

.scan-status-error {
  background-color: #ffebee;
  color: #d32f2f;
  border: 1px solid #ffcdd2;
}

.device-group {
  margin-bottom: 20px;
  padding: 16px;
  background-color: #ffffff;
  border: 1px solid #e9ecef;
  border-radius: 6px;
}

.device-group h5 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
  color: #495057;
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
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.checkbox-item:hover {
  background-color: #e3f2fd;
  border-color: #bbdefb;
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
  background-color: #e3f2fd;
  border: 1px solid #bbdefb;
  border-radius: 6px;
  font-size: 14px;
  color: #1976d2;
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-description i {
  font-size: 16px;
}

.modal-footer {
  padding: 20px 24px;
  border-top: 1px solid #e9ecef;
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

.btn-primary {
  background-color: #007bff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background-color: #0056b3;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.3);
}

.btn-primary:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.btn-secondary {
  background-color: #f8f9fa;
  color: #6c757d;
  border: 1px solid #dee2e6;
}

.btn-secondary:hover {
  background-color: #e9ecef;
  color: #495057;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style>
