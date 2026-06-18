<template>
  <div class="voiceprint-editor">
    <div class="vp-header">
      <span class="vp-title">
        <i class="fas fa-fingerprint"></i> 声纹注册配置
      </span>
      <label class="vp-switch">
        <input type="checkbox" v-model="enabled" @change="onToggle" />
        <span class="vp-switch-label">{{ enabled ? '启用' : '关闭' }}</span>
      </label>
    </div>

    <div v-if="enabled" class="vp-body">
      <!-- 注册音频 -->
      <div class="vp-field">
        <label class="vp-field-label">注册音频</label>
        <div class="vp-audio-row">
          <input
            type="text"
            class="form-control form-control-sm vp-audio-input"
            :value="voiceprintAudioId"
            placeholder="请选择音频..."
            readonly
            @click="openAudioModal"
          />
          <button
            type="button"
            class="btn btn-sm btn-outline-primary"
            @click="openAudioModal"
          >
            <i class="fas fa-music"></i> 选择
          </button>
          <button
            v-if="voiceprintAudioId"
            type="button"
            class="btn btn-sm btn-outline-danger"
            @click="clearAudio"
          >
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>

      <!-- 播放设备 -->
      <div class="vp-field">
        <label class="vp-field-label">播放设备</label>
        <select
          class="form-control form-control-sm"
          :value="voiceprintPlaybackDeviceId"
          @change="setParam('voiceprintPlaybackDeviceId', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">请选择设备...</option>
          <option
            v-for="dev in playbackDevices"
            :key="dev.id"
            :value="String(dev.id)"
          >{{ dev.name }}</option>
        </select>
      </div>

      <!-- 播放声压级 -->
      <div class="vp-field">
        <label class="vp-field-label">播放声压级 (dB)</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="voiceprintSpl"
          min="40"
          max="100"
          step="1"
          @input="setParam('voiceprintSpl', Number(($event.target as HTMLInputElement).value))"
        />
      </div>

      <!-- 等待时间 -->
      <div class="vp-field">
        <label class="vp-field-label">注册后等待 (秒)</label>
        <input
          type="number"
          class="form-control form-control-sm"
          :value="voiceprintWaitTime"
          min="0"
          max="60"
          step="1"
          @input="setParam('voiceprintWaitTime', Number(($event.target as HTMLInputElement).value))"
        />
        <span class="vp-hint">声纹注册完成后等待设备处理的时间</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import type { AlgorithmParamItem } from './types'
import type { PlaybackDevice } from '../../../../shared/types'

const props = defineProps<{
  modelValue: AlgorithmParamItem[]
  fieldCode?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AlgorithmParamItem[]]
  'openAudioModal': [callback: (audioId: string) => void]
}>()

// inject playback devices from parent (RoundConfigEditor or CaseForm)
const playbackDevices = inject<PlaybackDevice[]>('playbackDevices', [])

// ---- algorithmParams 读写 ----
function getParam(fieldCode: string, defaultValue: unknown = ''): unknown {
  const item = props.modelValue?.find((p) => p.field_code === fieldCode)
  return item?.field_value ?? defaultValue
}

function setParam(fieldCode: string, value: unknown) {
  const params = [...(props.modelValue ?? [])]
  const idx = params.findIndex((p) => p.field_code === fieldCode)
  if (idx >= 0) {
    params[idx] = { field_code: fieldCode, field_value: value }
  } else {
    params.push({ field_code: fieldCode, field_value: value })
  }
  emit('update:modelValue', params)
}

// ---- 计算属性 ----
const enabled = computed({
  get: () => {
    const v = getParam('voiceprintEnabled', false)
    return v === true || v === 'true'
  },
  set: (val: boolean) => setParam('voiceprintEnabled', val),
})

const voiceprintAudioId = computed(() => String(getParam('voiceprintAudioId', '') || ''))
const voiceprintPlaybackDeviceId = computed(() => String(getParam('voiceprintPlaybackDeviceId', '') || ''))
const voiceprintSpl = computed(() => Number(getParam('voiceprintSpl', 70)))
const voiceprintWaitTime = computed(() => Number(getParam('voiceprintWaitTime', 5)))

function onToggle() {
  // When enabling, ensure defaults exist
  if (enabled.value) {
    if (!voiceprintSpl.value || voiceprintSpl.value === 0) {
      setParam('voiceprintSpl', 70)
    }
    if (!voiceprintWaitTime.value && voiceprintWaitTime.value !== 0) {
      setParam('voiceprintWaitTime', 5)
    }
  }
}

function openAudioModal() {
  emit('openAudioModal', (audioId: string) => {
    setParam('voiceprintAudioId', audioId)
  })
}

function clearAudio() {
  setParam('voiceprintAudioId', '')
}
</script>

<style scoped>
.voiceprint-editor {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.vp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--background-secondary, #f5f5f5);
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.vp-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  display: flex;
  align-items: center;
  gap: 6px;
}
.vp-title i {
  font-size: 12px;
  color: var(--text-light, #999);
}

.vp-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
}
.vp-switch input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary-color, #ff6a00);
}
.vp-switch-label {
  color: var(--text-secondary, #666);
}

.vp-body {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.vp-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vp-field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #666);
}

.vp-audio-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.vp-audio-input {
  flex: 1;
  cursor: pointer;
  background: var(--background-primary, #fff) !important;
}

.vp-hint {
  font-size: 11px;
  color: var(--text-light, #999);
  margin-top: 2px;
}
</style>
