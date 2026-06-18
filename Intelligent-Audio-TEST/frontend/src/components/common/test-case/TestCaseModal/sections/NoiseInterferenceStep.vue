<template>
  <div class="rce-step" id="step-noise">
    <div class="rce-step-header">
      <i class="fas fa-volume-up rce-step-icon"></i>
      <span class="rce-step-title">噪声 & 干扰</span>
      <span class="rce-tag rce-tag-gray">backgroundNoise + algorithmParams</span>
    </div>

    <!-- 背景噪声 -->
    <div class="rce-section">
      <div class="rce-sub-title">
        <i class="fas fa-volume-up"></i> 背景噪声
      </div>
      <div class="rce-noise-body">
        <div class="rce-field">
          <label class="rce-field-label">噪声音频</label>
          <div class="rce-audio-input">
            <input
              type="text"
              class="form-control form-control-sm"
              :value="round.backgroundNoise?.audioId || ''"
              placeholder="选择噪声..."
              readonly
              @click="openNoiseAudioModal"
            />
            <button type="button" class="btn btn-sm btn-outline-primary" @click="openNoiseAudioModal">
              <i class="fas fa-music"></i>
            </button>
            <button
              v-if="round.backgroundNoise?.audioId"
              type="button"
              class="btn btn-sm btn-outline-danger"
              @click="clearNoise"
            >
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>
        <div class="rce-field-row">
          <div class="rce-field" style="flex:1">
            <label class="rce-field-label">声压级 (dB)</label>
            <input
              type="number"
              class="form-control form-control-sm"
              :value="round.backgroundNoise?.spl ?? 0"
              min="0" max="120" step="1"
              @input="updateNoise('spl', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
          <div class="rce-field" style="flex:1">
            <label class="rce-field-label">循环播放</label>
            <label class="rce-switch">
              <input
                type="checkbox"
                :checked="round.backgroundNoise?.loop ?? false"
                @change="updateNoise('loop', ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ round.backgroundNoise?.loop ? '是' : '否' }}</span>
            </label>
          </div>
        </div>
        <div class="rce-field">
          <label class="rce-field-label">播放设备</label>
          <select
            class="form-control form-control-sm"
            :value="(round.backgroundNoise?.deviceIds || [])[0] || ''"
            @change="updateNoiseDeviceIds(($event.target as HTMLSelectElement).value)"
          >
            <option value="">请选择...</option>
            <option v-for="dev in playbackDevices" :key="dev.id" :value="String(dev.id)">{{ dev.name }}</option>
          </select>
        </div>
      </div>
    </div>

    <!-- 声纹注册 -->
    <div class="rce-section" v-if="hasVoiceprintParam">
      <VoiceprintConfigEditor
        :model-value="round.algorithmParams || []"
        @update:model-value="(v: AlgorithmParamItem[]) => emit('update:round', { ...round, algorithmParams: v })"
        @open-audio-modal="(cb: (audioId: string) => void) => emit('openAudioSelect', cb)"
      />
    </div>

    <!-- 干扰人 -->
    <div class="rce-section" v-if="hasInterfererParam">
      <InterfererConfigEditor
        :model-value="round.algorithmParams || []"
        @update:model-value="(v: AlgorithmParamItem[]) => emit('update:round', { ...round, algorithmParams: v })"
        @open-audio-modal="(cb: (audioId: string, audioName?: string) => void) => emit('openAudioSelect', cb)"
      />
    </div>

    <!-- 打断检测 -->
    <div class="rce-section" v-if="hasInterruptionParam">
      <div class="rce-sub-title">
        <i class="fas fa-hand-paper"></i> 打断检测
      </div>
      <div class="rce-param-grid">
        <div class="rce-param-item">
          <label class="rce-param-label">启用打断检测</label>
          <label class="rce-switch">
            <input
              type="checkbox"
              :checked="isTruthy(getAlgoParam('interruptionEnabled', false))"
              @change="setAlgoParam('interruptionEnabled', ($event.target as HTMLInputElement).checked)"
            />
            <span>{{ isTruthy(getAlgoParam('interruptionEnabled')) ? '启用' : '关闭' }}</span>
          </label>
        </div>
        <div class="rce-param-item" v-if="isTruthy(getAlgoParam('interruptionEnabled'))">
          <label class="rce-param-label">灵敏度</label>
          <div class="rce-slider-wrap">
            <input
              type="range"
              class="rce-slider"
              min="0" max="100" step="1"
              :value="getAlgoParam('interruptionSensitivity', 50)"
              @input="setAlgoParam('interruptionSensitivity', Number(($event.target as HTMLInputElement).value))"
            />
            <span class="rce-slider-val">{{ getAlgoParam('interruptionSensitivity', 50) }}%</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RoundConfigItem, AlgorithmParamItem, BackgroundNoiseConfig } from '../types'
import type { PlaybackDevice } from '../../../../../shared/types'
import { inject } from 'vue'
import VoiceprintConfigEditor from '../VoiceprintConfigEditor.vue'
import InterfererConfigEditor from '../InterfererConfigEditor.vue'

const props = defineProps<{
  round: RoundConfigItem
  playbackDevices: PlaybackDevice[]
  hasVoiceprintParam: boolean
  hasInterfererParam: boolean
  hasInterruptionParam: boolean
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
  'openAudioSelect': [callback: (audioId: string) => void]
}>()

function getAlgoParam(fieldCode: string, defaultValue?: unknown): unknown {
  const params = props.round.algorithmParams || []
  const item = params.find((p) => p.field_code === fieldCode)
  return item?.field_value ?? defaultValue ?? ''
}

function setAlgoParam(fieldCode: string, value: unknown) {
  const params = [...(props.round.algorithmParams || [])]
  const idx = params.findIndex((p) => p.field_code === fieldCode)
  if (idx >= 0) {
    params[idx] = { field_code: fieldCode, field_value: value }
  } else {
    params.push({ field_code: fieldCode, field_value: value })
  }
  emit('update:round', { ...props.round, algorithmParams: params })
}

function isTruthy(val: unknown): boolean {
  return val === true || val === 'true' || val === 1
}

function updateNoise(key: string, value: unknown) {
  const noise = { ...(props.round.backgroundNoise || { audioId: '', deviceIds: [], spl: 0 }) }
  ;(noise as any)[key] = value
  emit('update:round', { ...props.round, backgroundNoise: noise as BackgroundNoiseConfig })
}

function updateNoiseDeviceIds(deviceId: string) {
  updateNoise('deviceIds', deviceId ? [deviceId] : [])
}

function clearNoise() {
  emit('update:round', { ...props.round, backgroundNoise: undefined })
}

function openNoiseAudioModal() {
  emit('openAudioSelect', (audioId: string) => {
    updateNoise('audioId', audioId)
  })
}
</script>

<style scoped>
.rce-step {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}
.rce-step:last-child { border-bottom: none; }

.rce-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rce-step-icon { font-size: 14px; color: var(--primary-color, #ff6a00); }
.rce-step-title { font-size: 14px; font-weight: 600; color: var(--text-primary, #333); }

.rce-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
}
.rce-tag-gray { background: #f5f5f5; color: #999; }

.rce-section { margin-bottom: 14px; }

.rce-sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.rce-sub-title i { font-size: 12px; color: var(--text-light, #999); }

.rce-noise-body {
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rce-field { display: flex; flex-direction: column; gap: 3px; }
.rce-field-row { display: flex; gap: 12px; }
.rce-field-label { font-size: 12px; font-weight: 500; color: var(--text-secondary, #666); }

.rce-audio-input { display: flex; gap: 4px; align-items: center; }
.rce-audio-input input {
  flex: 1;
  cursor: pointer;
  background: var(--background-primary, #fff) !important;
}

.rce-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary, #666);
}
.rce-switch input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary-color, #ff6a00);
}

.rce-param-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.rce-param-item { flex: 1; min-width: 160px; max-width: 320px; }
.rce-param-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #666);
  margin-bottom: 4px;
}

.rce-slider-wrap { display: flex; align-items: center; gap: 8px; }
.rce-slider {
  flex: 1;
  -webkit-appearance: none;
  height: 4px;
  border-radius: 2px;
  background: var(--border-color, #e0e0e0);
  outline: none;
}
.rce-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--primary-color, #ff6a00);
  cursor: pointer;
}
.rce-slider-val {
  font-size: 12px;
  color: var(--primary-color, #ff6a00);
  font-weight: 600;
  min-width: 40px;
  text-align: right;
}
</style>
