<!-- MVC role: View（INT-2044：音频试听配置——播放模式 / 播放设备 / 声压级 / 偏移量） -->
<template>
  <teleport to="body">
    <div v-if="visible" class="modal-overlay">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">试听配置</h3>
          <button type="button" class="modal-close" @click="handleClose">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <p class="preview-audio-name">
            <i class="fas fa-file-audio"></i>
            {{ audioTitle || '未知音频' }}
          </p>

          <div class="config-section">
            <span class="config-label">播放模式</span>
            <div class="radio-group">
              <label class="radio-item">
                <input type="radio" value="frontend" v-model="playbackMode" />
                <span>浏览器播放</span>
              </label>
              <label class="radio-item">
                <input type="radio" value="backend" v-model="playbackMode" />
                <span>实验室播放</span>
              </label>
            </div>
            <p class="mode-description">
              <i class="fas fa-info-circle"></i>
              {{ playbackMode === 'frontend' ? '音频通过当前浏览器扬声器播放' : '音频通过所选播放设备在实验室输出' }}
            </p>
          </div>

          <div class="config-section" v-if="playbackMode === 'backend'">
            <span class="config-label">播放设备</span>
            <select
              v-if="playbackDevices.length > 0"
              v-model="selectedDeviceId"
              class="form-control"
              aria-label="播放设备"
            >
              <option v-for="device in playbackDevices" :key="device.id" :value="String(device.id)">
                {{ device.name }}{{ device.model ? `（${device.model}）` : '' }}
              </option>
            </select>
            <div v-else class="device-empty">
              <i class="fas fa-headphones"></i>
              <p>暂无可用的播放设备</p>
              <span>请先在「设备管理」中添加播放设备，或改用浏览器播放</span>
            </div>

            <div class="config-inline" v-if="playbackDevices.length > 0">
              <label class="inline-field">
                <span class="config-label">声压级（dB）</span>
                <input
                  type="number"
                  class="form-control inline-input"
                  min="30"
                  max="120"
                  v-model.number="spl"
                  aria-label="声压级"
                />
              </label>
              <label class="inline-field">
                <span class="config-label">偏移量（秒）</span>
                <input
                  type="number"
                  class="form-control inline-input"
                  min="0"
                  v-model.number="offset"
                  aria-label="偏移量"
                />
              </label>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="handleClose">取消</button>
          <button type="button" class="btn btn-primary" :disabled="!canConfirm" @click="handleConfirm">
            <i class="fas fa-play"></i> 开始试听
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed, ref, watch, onUnmounted } from 'vue'
import type { PlaybackDevice } from '../../domain';
import { DEFAULT_PREVIEW_SPL, type AudioPreviewConfig, type PreviewPlaybackMode } from './AudioPreviewConfigModal';

const props = withDefaults(defineProps<{
  visible: boolean;
  audioTitle?: string;
  playbackDevices?: PlaybackDevice[];
  initialPlaybackMode?: PreviewPlaybackMode;
  initialDeviceId?: string;
  initialSpl?: number;
  initialOffset?: number;
}>(), {
  audioTitle: '',
  playbackDevices: () => [],
  initialPlaybackMode: 'frontend',
  initialDeviceId: '',
  initialSpl: DEFAULT_PREVIEW_SPL,
  initialOffset: 0
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'confirm', config: AudioPreviewConfig): void;
}>();

const playbackMode = ref<PreviewPlaybackMode>('frontend');
const selectedDeviceId = ref('');
const spl = ref(DEFAULT_PREVIEW_SPL);
const offset = ref(0);

/** 选中设备失效（列表变化 / 无设备）时回退到首台可用设备 */
const resolveDeviceId = (): string => {
  const devices = props.playbackDevices || [];
  if (props.initialDeviceId && devices.some(d => String(d.id) === props.initialDeviceId)) {
    return props.initialDeviceId;
  }
  return devices.length > 0 ? String(devices[0].id) : '';
};

const selectedDevice = computed<PlaybackDevice | null>(() =>
  (props.playbackDevices || []).find(d => String(d.id) === selectedDeviceId.value) ?? null
);

const canConfirm = computed(() => playbackMode.value !== 'backend' || !!selectedDevice.value);

const resetForm = () => {
  playbackMode.value = props.initialPlaybackMode || 'frontend';
  selectedDeviceId.value = resolveDeviceId();
  spl.value = props.initialSpl ?? DEFAULT_PREVIEW_SPL;
  offset.value = props.initialOffset ?? 0;
};

watch(() => props.visible, (newValue) => {
  if (newValue) resetForm();
}, { immediate: true });

watch(() => props.playbackDevices, () => {
  if (!props.visible) return;
  const stillValid = (props.playbackDevices || []).some(d => String(d.id) === selectedDeviceId.value);
  if (!stillValid) selectedDeviceId.value = resolveDeviceId();
}, { deep: true });

const handleClose = () => {
  emit('close');
};

const handleKeyDown = (event: KeyboardEvent) => {
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

const handleConfirm = () => {
  if (!canConfirm.value) return;
  emit('confirm', {
    playbackMode: playbackMode.value,
    device: playbackMode.value === 'backend' ? selectedDevice.value : null,
    spl: spl.value ?? DEFAULT_PREVIEW_SPL,
    offset: offset.value ?? 0
  });
  handleClose();
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background-color: color-mix(in srgb, var(--color-black) 50%, transparent);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: calc(var(--z-index-modal-top, 13000) + 2);
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background-color: var(--background);
  border-radius: var(--radius-card);
  box-shadow: 0 4px 20px color-mix(in srgb, var(--color-black) 15%, transparent);
  width: 90%;
  max-width: 520px;
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
  padding: var(--spacing-lg) var(--spacing-xl);
  border-bottom: 1px solid var(--muted);
  background: linear-gradient(135deg, var(--muted) 0%, var(--muted) 100%);
}

.modal-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--foreground);
}

.modal-close {
  background: none;
  border: none;
  font-size: var(--font-size-xl);
  cursor: pointer;
  color: var(--muted-foreground);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  transition: all var(--transition-normal);
}

.modal-close:hover {
  color: var(--foreground);
  background-color: var(--muted);
  transform: rotate(90deg);
}

.modal-body {
  padding: var(--spacing-xl);
}

.preview-audio-name {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0 0 var(--spacing-lg);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--foreground);
  word-break: break-all;
}

.config-section {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-lg);
  background-color: var(--muted);
  border: 1px solid var(--muted);
  border-radius: var(--radius-control);
}

.config-label {
  display: block;
  margin-bottom: var(--spacing-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--muted-foreground);
}

.radio-group {
  display: flex;
  gap: var(--spacing-lg);
}

.radio-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--foreground);
}

.radio-item input[type="radio"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.mode-description {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: var(--spacing-md) 0 0;
  padding: var(--spacing-md);
  background-color: var(--color-secondary-light);
  border: 1px solid var(--color-secondary-light);
  border-radius: var(--radius-control);
  font-size: var(--font-size-sm);
  color: var(--secondary);
}

.form-control {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background-color: var(--background);
  color: var(--foreground);
  font-size: var(--font-size-sm);
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 0.2rem color-mix(in srgb, var(--secondary) 25%, transparent);
}

.config-inline {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-lg);
  margin-top: var(--spacing-md);
}

.inline-field {
  display: flex;
  flex-direction: column;
  min-width: 140px;
}

.inline-input {
  width: 140px;
}

.device-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-lg);
  color: var(--muted-foreground);
  text-align: center;
}

.device-empty i {
  font-size: var(--font-size-2xl);
  opacity: 0.5;
}

.device-empty p {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.device-empty span {
  font-size: var(--font-size-xs);
}

.modal-footer {
  padding: var(--spacing-lg) var(--spacing-xl);
  border-top: 1px solid var(--muted);
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-md);
}

.btn {
  padding: var(--spacing-sm) var(--spacing-xl);
  border: none;
  border-radius: var(--radius-control);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-normal);
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
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
</style>
