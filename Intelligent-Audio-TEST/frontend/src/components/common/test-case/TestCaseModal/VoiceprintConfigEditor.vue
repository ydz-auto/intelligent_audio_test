<template>
  <div class="voiceprint-editor">
    <div class="vp-header">
      <span class="vp-title">
        <i class="fas fa-fingerprint"></i> 声纹注册配置
      </span>
      <button
        v-if="!enabled"
        type="button"
        class="btn btn-sm btn-outline-primary"
        @click="addVoiceprint"
      >
        <i class="fas fa-plus"></i> 添加声纹注册
      </button>
      <button
        v-else
        type="button"
        class="vp-remove-btn"
        @click="removeVoiceprint"
      >
        <i class="fas fa-trash-alt"></i> 移除
      </button>
    </div>

    <div v-if="enabled" class="vp-body">
      <!-- 注册音频 — 音频卡片样式 -->
      <div class="vp-field">
        <label class="vp-field-label">注册音频</label>
        <div v-if="voiceprintAudioId" class="vp-audio-card">
          <div class="vp-audio-card-info">
            <div class="vp-audio-card-row">
              <i class="fas fa-music vp-audio-card-icon"></i>
              <span class="vp-audio-card-name" :title="getAudioName(voiceprintAudioId)">
                {{ getAudioName(voiceprintAudioId) }}
              </span>
              <span class="vp-audio-card-duration" v-if="getAudioDuration(voiceprintAudioId) > 0">
                <i class="fas fa-clock"></i> {{ formatDuration(getAudioDuration(voiceprintAudioId)) }}
              </span>
            </div>
            <div class="vp-audio-card-tags" v-if="getAudioTags(voiceprintAudioId)">
              <span class="vp-audio-tag" v-for="tag in getNormalizedTags(getAudioTags(voiceprintAudioId))" :key="tag">{{ tag }}</span>
            </div>
          </div>
          <div class="vp-audio-card-actions">
            <button type="button" class="btn btn-sm btn-outline-primary" @click="openAudioModal">
              <i class="fas fa-exchange-alt"></i> 更换
            </button>
            <button type="button" class="btn btn-sm btn-outline-info" @click="previewAudio">
              <i class="fas fa-play"></i> 试听
            </button>
            <button type="button" class="btn btn-sm btn-outline-danger" @click="clearAudio">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>
        <div v-else class="vp-audio-empty" @click="openAudioModal">
          <i class="fas fa-plus-circle"></i>
          <span>选择注册音频</span>
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
  'previewAudio': [audioId: string]
}>()

// inject audioConfig 和 playback devices from parent
const audioConfig = inject<any>('audioConfig', {})
const playbackDevices = inject<PlaybackDevice[]>('playbackDevices', [])

// ---- 音频信息查询 ----
function getAudioName(audioId: string | number): string {
  return audioConfig?.getAudioName?.(audioId) || '未知音频'
}

function getAudioTags(audioId: string | number): string {
  return audioConfig?.getAudioTags?.(audioId) || ''
}

function getAudioDuration(audioId: string | number): number {
  return audioConfig?.getAudioDuration?.(audioId) || 0
}

function formatDuration(seconds: number): string {
  return audioConfig?.formatDuration?.(seconds) || '0s'
}

function getNormalizedTags(tagsStr: string): string[] {
  if (!tagsStr) return []
  try {
    const parsed = JSON.parse(tagsStr)
    if (Array.isArray(parsed)) return parsed.map(String)
    if (typeof parsed === 'string') return parsed.split(',').map((s: string) => s.trim()).filter(Boolean)
  } catch {
    return String(tagsStr).split(',').map((s: string) => s.trim()).filter(Boolean)
  }
  return []
}

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

function addVoiceprint() {
  setParam('voiceprintEnabled', true)
  setParam('voiceprintSpl', 70)
  setParam('voiceprintWaitTime', 5)
}

function removeVoiceprint() {
  setParam('voiceprintEnabled', false)
  setParam('voiceprintAudioId', '')
  setParam('voiceprintPlaybackDeviceId', '')
  setParam('voiceprintSpl', '')
  setParam('voiceprintWaitTime', '')
}

function openAudioModal() {
  emit('openAudioModal', (audioId: string) => {
    setParam('voiceprintAudioId', audioId)
  })
}

function previewAudio() {
  if (voiceprintAudioId.value) {
    emit('previewAudio', voiceprintAudioId.value)
  }
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

.vp-remove-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--danger-color, #f44336);
  border-radius: 4px;
  background: transparent;
  color: var(--danger-color, #f44336);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}
.vp-remove-btn:hover {
  background: var(--danger-color, #f44336);
  color: #fff;
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

.vp-hint {
  font-size: 11px;
  color: var(--text-light, #999);
  margin-top: 2px;
}

/* 音频卡片样式 */
.vp-audio-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #e0e7ff;
  border-radius: 6px;
  background: #f8f9ff;
}
.vp-audio-card-info {
  flex: 1;
  min-width: 0;
}
.vp-audio-card-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.vp-audio-card-icon {
  color: #6366f1;
  font-size: 12px;
}
.vp-audio-card-name {
  font-size: 13px;
  font-weight: 500;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.vp-audio-card-duration {
  font-size: 11px;
  color: #999;
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.vp-audio-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.vp-audio-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: #e0e7ff;
  color: #4f46e5;
}
.vp-audio-card-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.vp-audio-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  cursor: pointer;
  color: #999;
  font-size: 13px;
  transition: all 0.15s;
}
.vp-audio-empty:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #f8f9ff;
}
</style>
