<template>
  <div class="global-noise-editor">
    <!-- 标题区 -->
    <div class="global-noise-header">
      <div class="global-noise-icon">
        <i class="fas fa-volume-up"></i>
      </div>
      <div class="global-noise-title-group">
        <div class="global-noise-title">
          全局背景噪声
          <span class="global-noise-badge">所有轮次共享</span>
        </div>
        <div class="global-noise-subtitle">config.background_noise — 轮次内未配置噪声时回退使用</div>
      </div>
    </div>

    <!-- 描述说明 -->
    <div class="global-noise-description">
      全局背景噪声在<span class="highlight">每轮播放干声期间</span>循环播放。
      当某轮次已配置轮次级背景噪声时，该轮<span class="highlight">不播放</span>全局噪声；
      当某轮次未配置轮次级背景噪声时，该轮<span class="highlight">回退播放</span>全局噪声。
    </div>

    <!-- 添加/移除按钮 -->
    <div class="global-noise-toggle-row">
      <button
        v-if="!noiseConfig?.audioId"
        type="button"
        class="btn btn-sm btn-outline-primary"
        @click="addNoise"
      >
        <i class="fas fa-plus"></i> 添加全局噪声
      </button>
      <button
        v-else
        type="button"
        class="btn btn-sm btn-outline-danger"
        @click="clearNoise"
      >
        <i class="fas fa-trash-alt"></i> 移除
      </button>
    </div>

    <!-- 噪声配置区 -->
    <div v-if="noiseConfig?.audioId" class="global-noise-body">
      <!-- 噪声音频卡片 -->
      <div class="global-noise-field">
        <label class="global-noise-field-label">噪声音频</label>
        <div class="global-noise-card">
          <div class="global-noise-card-info">
            <div class="global-noise-card-row">
              <i class="fas fa-music global-noise-card-icon"></i>
              <span class="global-noise-card-name" :title="getAudioName(noiseConfig.audioId)">
                {{ getAudioName(noiseConfig.audioId) }}
              </span>
              <span class="global-noise-card-duration" v-if="getAudioDuration(noiseConfig.audioId) > 0">
                <i class="fas fa-clock"></i> {{ formatDuration(getAudioDuration(noiseConfig.audioId)) }}
              </span>
            </div>
          </div>
          <div class="global-noise-card-actions">
            <button type="button" class="btn btn-sm btn-outline-primary" @click="openNoiseAudioModal">
              <i class="fas fa-exchange-alt"></i> 更换
            </button>
            <button type="button" class="btn btn-sm btn-outline-info" @click="previewNoise">
              <i class="fas fa-play"></i> 试听
            </button>
          </div>
        </div>
      </div>

      <div class="global-noise-field-row">
        <div class="global-noise-field" style="flex:1">
          <label class="global-noise-field-label">声压级 (dB)</label>
          <input
            type="number"
            class="form-control form-control-sm"
            :value="noiseConfig?.spl ?? 0"
            min="0" max="120" step="1"
            @input="updateNoise('spl', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="global-noise-field" style="flex:1">
          <label class="global-noise-field-label">循环播放</label>
          <label class="global-noise-switch">
            <input
              type="checkbox"
              :checked="noiseConfig?.loop ?? true"
              @change="updateNoise('loop', ($event.target as HTMLInputElement).checked)"
            />
            <span>{{ noiseConfig?.loop ? '是' : '否' }}</span>
          </label>
        </div>
      </div>

      <div class="global-noise-field-row">
        <div class="global-noise-field" style="flex:1">
          <label class="global-noise-field-label">播放设备</label>
          <select
            class="form-control form-control-sm"
            :value="(noiseConfig?.deviceIds || [])[0] || ''"
            @change="updateDeviceIds(($event.target as HTMLSelectElement).value)"
          >
            <option value="">请选择...</option>
            <option v-for="dev in playbackDevices" :key="dev.id" :value="String(dev.id)">{{ dev.name }}</option>
          </select>
        </div>
      </div>
    </div>
    <div v-else class="global-noise-empty">
      <i class="fas fa-info-circle"></i>
      未配置全局背景噪声，轮次内未配置噪声时将无声播放
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BackgroundNoiseConfig, PlaybackDevice } from './types'
import { inject, computed } from 'vue'

const props = defineProps<{
  modelValue?: BackgroundNoiseConfig | Record<string, unknown> | null
  playbackDevices: PlaybackDevice[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: BackgroundNoiseConfig | null]
  'openAudioSelect': [audioType: 'dry' | 'noise', callback: (audios: { id: string; name?: string }[]) => void]
  'previewAudio': [audioId: string]
}>()

const audioConfig = inject<any>('audioConfig', {})

const noiseConfig = computed<BackgroundNoiseConfig | null>(() => {
  const v = props.modelValue
  if (!v || (typeof v === 'object' && !(v as any).audioId)) return null
  return v as BackgroundNoiseConfig
})

function getAudioName(audioId: string): string {
  return audioConfig?.getAudioName?.(audioId) || audioId
}

function getAudioDuration(audioId: string): number {
  return audioConfig?.getAudioDuration?.(audioId) || 0
}

function formatDuration(seconds: number): string {
  return audioConfig?.formatDuration?.(seconds) || '0s'
}

function addNoise() {
  emit('update:modelValue', { audioId: '', deviceIds: [], spl: 60, loop: true })
}

function clearNoise() {
  emit('update:modelValue', null)
}

function updateNoise(field: string, value: unknown) {
  if (!noiseConfig.value) return
  emit('update:modelValue', { ...noiseConfig.value, [field]: value })
}

function updateDeviceIds(deviceId: string) {
  if (!noiseConfig.value) return
  const ids = deviceId ? [deviceId] : []
  emit('update:modelValue', { ...noiseConfig.value, deviceIds: ids })
}

function openNoiseAudioModal() {
  emit('openAudioSelect', 'noise', (audios: { id: string; name?: string }[]) => {
    if (audios.length > 0 && noiseConfig.value) {
      emit('update:modelValue', { ...noiseConfig.value, audioId: audios[0].id })
    }
  })
}

function previewNoise() {
  if (noiseConfig.value?.audioId) {
    emit('previewAudio', noiseConfig.value.audioId)
  }
}
</script>

<style scoped>
.global-noise-editor {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
}
.global-noise-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.global-noise-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e3f2fd;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #1976d2;
  font-size: 16px;
}
.global-noise-title-group {
  flex: 1;
}
.global-noise-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  display: flex;
  align-items: center;
  gap: 8px;
}
.global-noise-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #e8f5e9;
  color: #2e7d32;
}
.global-noise-subtitle {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
}
.global-noise-description {
  font-size: 12px;
  color: #666;
  line-height: 1.6;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fff3e0;
  border-radius: 6px;
}
.global-noise-description .highlight {
  color: #e65100;
  font-weight: 500;
}
.global-noise-toggle-row {
  margin-bottom: 12px;
}
.global-noise-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.global-noise-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.global-noise-field-label {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}
.global-noise-field-row {
  display: flex;
  gap: 12px;
}
.global-noise-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: #fff;
}
.global-noise-card-info {
  flex: 1;
  min-width: 0;
}
.global-noise-card-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.global-noise-card-icon {
  color: #1976d2;
  font-size: 14px;
}
.global-noise-card-name {
  font-size: 13px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.global-noise-card-duration {
  font-size: 11px;
  color: #888;
}
.global-noise-card-actions {
  display: flex;
  gap: 6px;
}
.global-noise-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #555;
}
.global-noise-empty {
  font-size: 13px;
  color: #999;
  padding: 12px;
  text-align: center;
}
</style>
