<template>
  <div class="audio-select-editor">
    <div class="as-header">
      <span class="as-title">
        <i class="fas fa-music"></i> {{ paramName }}
      </span>
    </div>

    <div class="as-body">
      <div v-if="audioId" class="as-audio-card">
        <div class="as-audio-card-info">
          <div class="as-audio-card-row">
            <i class="fas fa-music as-audio-card-icon"></i>
            <span class="as-audio-card-name" :title="audioName">{{ audioName }}</span>
            <span class="as-audio-card-duration" v-if="audioDuration > 0">
              <i class="fas fa-clock"></i> {{ formatDuration(audioDuration) }}
            </span>
          </div>
          <div class="as-audio-card-tags" v-if="audioTags">
            <span class="as-audio-tag" v-for="tag in normalizedTags" :key="tag">{{ tag }}</span>
          </div>
        </div>
        <div class="as-audio-card-actions">
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
      <div v-else class="as-audio-empty" @click="openAudioModal">
        <i class="fas fa-plus-circle"></i>
        <span>选择{{ paramName }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import type { AlgorithmParamItem } from './types'

const props = defineProps<{
  modelValue: AlgorithmParamItem[]
  paramName: string
  fieldCode: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AlgorithmParamItem[]]
  'openAudioSelect': [callback: (audios: { id: string; name?: string }[]) => void]
  'previewAudio': [audioId: string]
}>()

const audioConfig = inject<any>('audioConfig', {})

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

// ---- 参数读写 ----
const audioId = computed(() => {
  const item = props.modelValue?.find((p) => p.field_code === props.fieldCode)
  const v = item?.field_value
  return v ? String(v) : ''
})
const audioName = computed(() => getAudioName(audioId.value))
const audioDuration = computed(() => getAudioDuration(audioId.value))
const audioTags = computed(() => getAudioTags(audioId.value))
const normalizedTags = computed(() => getNormalizedTags(audioTags.value))

function setAudioId(audioId: string) {
  const params = [...(props.modelValue ?? [])]
  const idx = params.findIndex((p) => p.field_code === props.fieldCode)
  if (idx >= 0) {
    params[idx] = { field_code: props.fieldCode, field_value: audioId }
  } else {
    params.push({ field_code: props.fieldCode, field_value: audioId })
  }
  emit('update:modelValue', params)
}

function openAudioModal() {
  emit('openAudioSelect', (audios: { id: string; name?: string }[]) => {
    if (audios.length > 0) setAudioId(String(audios[0].id))
  })
}
function previewAudio() {
  if (audioId.value) emit('previewAudio', audioId.value)
}
function clearAudio() {
  setAudioId('')
}
</script>

<style scoped>
.audio-select-editor {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.as-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--background-secondary, #f5f5f5);
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.as-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  display: flex;
  align-items: center;
  gap: 6px;
}
.as-title i {
  font-size: 12px;
  color: var(--text-light, #999);
}

.as-body { padding: 14px; }

.as-audio-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #e0e7ff;
  border-radius: 6px;
  background: #f8f9ff;
}
.as-audio-card-info { flex: 1; min-width: 0; }
.as-audio-card-row { display: flex; align-items: center; gap: 6px; }
.as-audio-card-icon { color: #6366f1; font-size: 12px; }
.as-audio-card-name {
  font-size: 13px; font-weight: 500; color: #333;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
}
.as-audio-card-duration {
  font-size: 11px; color: #999;
  display: flex; align-items: center; gap: 3px; white-space: nowrap;
}
.as-audio-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.as-audio-tag {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: #e0e7ff; color: #4f46e5;
}
.as-audio-card-actions { display: flex; gap: 4px; flex-shrink: 0; }

.as-audio-empty {
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
.as-audio-empty:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #f8f9ff;
}
</style>
