<template>
  <div class="rce-step" id="step-noise">
    <div class="rce-step-header">
      <i class="fas fa-volume-up rce-step-icon"></i>
      <span class="rce-step-title">噪声 & 干扰</span>
      <span class="rce-tag rce-tag-gray">backgroundNoise + algorithmParams</span>
    </div>

    <!-- 背景噪声 -->
    <div class="rce-section">
      <div class="rce-noise-header">
        <span class="rce-noise-title">
          <i class="fas fa-volume-up"></i> 背景噪声
        </span>
        <button
          v-if="!hasNoiseAudio"
          type="button"
          class="btn btn-sm btn-outline-primary"
          @click="addNoise"
        >
          <i class="fas fa-plus"></i> 添加噪声
        </button>
        <button
          v-else
          type="button"
          class="rce-noise-remove-btn"
          @click="clearNoise"
        >
          <i class="fas fa-trash-alt"></i> 移除
        </button>
      </div>

      <div v-if="hasNoiseAudio" class="rce-noise-body">
        <!-- 噪声音频卡片 -->
        <div class="rce-field">
          <label class="rce-field-label">噪声音频</label>
          <div class="rce-noise-card">
            <div class="rce-noise-card-info">
              <div class="rce-noise-card-row">
                <i class="fas fa-music rce-noise-card-icon"></i>
                <span class="rce-noise-card-name" :title="noiseAudioDisplayName">
                  {{ noiseAudioDisplayName }}
                </span>
                <span class="rce-noise-card-duration" v-if="round.backgroundNoise?.audioId && getAudioDuration(round.backgroundNoise.audioId) > 0">
                  <i class="fas fa-clock"></i> {{ formatDuration(getAudioDuration(round.backgroundNoise.audioId)) }}
                </span>
              </div>
              <div class="rce-noise-card-tags" v-if="round.backgroundNoise?.audioId && getAudioTags(round.backgroundNoise.audioId)">
                <span class="rce-noise-tag" v-for="tag in getNormalizedTags(getAudioTags(round.backgroundNoise.audioId))" :key="tag">{{ tag }}</span>
              </div>
            </div>
            <div class="rce-noise-card-actions">
              <button type="button" class="btn btn-sm btn-outline-primary" @click="openNoiseAudioModal">
                <i class="fas fa-exchange-alt"></i> 更换
              </button>
              <button type="button" class="btn btn-sm btn-outline-info" v-if="round.backgroundNoise?.audioId" @click="previewNoise">
                <i class="fas fa-play"></i> 试听
              </button>
            </div>
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
          <label class="rce-field-label">播放设备（可多选）</label>
          <div class="rce-noise-devices">
            <label v-for="dev in playbackDevices" :key="dev.id" class="rce-noise-device-chip">
              <input
                type="checkbox"
                :value="String(dev.id)"
                :checked="isNoiseDeviceSelected(String(dev.id))"
                @change="toggleNoiseDevice(String(dev.id), ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ dev.name }}</span>
            </label>
            <!-- 兜底显示：设备名存在但未匹配到 ID 的设备 -->
            <span v-for="name in unmatchedNoiseDeviceNames" :key="name" class="rce-noise-device-unmatched" :title="`未匹配到播放设备ID：${name}`">
              <i class="fas fa-exclamation-triangle"></i> {{ name }}
            </span>
          </div>
        </div>
      </div>
      <div v-else class="rce-noise-empty">
        <i class="fas fa-info-circle"></i>
        未配置背景噪声，点击"添加噪声"开始配置
      </div>
    </div>

    <!-- 声纹注册 -->
    <div class="rce-section" v-if="hasVoiceprintParam">
      <VoiceprintConfigEditor
        :model-value="currentAlgoParams"
        @update:model-value="onAlgoParamsUpdate"
        @open-audio-modal="(cb: (audioId: string) => void) => emit('openAudioSelect', 'noise', (audios: { id: string; name?: string }[]) => { if (audios.length > 0) cb(audios[0].id) })"
        @preview-audio="(audioId: string) => emit('previewAudio', audioId)"
      />
    </div>

    <!-- 干扰人 -->
    <div class="rce-section" v-if="hasInterfererParam">
      <InterfererConfigEditor
        :model-value="currentAlgoParams"
        @update:model-value="onAlgoParamsUpdate"
        @open-audio-modal="(cb: (audioId: string, audioName?: string) => void) => emit('openAudioSelect', 'noise', (audios: { id: string; name?: string }[]) => { if (audios.length > 0) cb(audios[0].id, audios[0].name) })"
        @preview-audio="(audioId: string) => emit('previewAudio', audioId)"
      />
    </div>

  </div>
</template>

<script setup lang="ts">
import type { RoundConfigItem, AlgorithmParamItem, BackgroundNoiseConfig } from '../types'
import type { PlaybackDevice } from '../../../../../shared/types'
import { inject, computed } from 'vue'
import VoiceprintConfigEditor from '../VoiceprintConfigEditor.vue'
import InterfererConfigEditor from '../InterfererConfigEditor.vue'

const props = defineProps<{
  round: RoundConfigItem
  playbackDevices: PlaybackDevice[]
  hasVoiceprintParam: boolean
  hasInterfererParam: boolean
  /** 当前轮的算法参数（来自独立列 algorithm_params 按轮匹配后的 params 数组） */
  roundAlgorithmParams?: AlgorithmParamItem[]
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
  /** 算法参数更新（独立列格式 params 数组） */
  'update:round-algo-params': [params: AlgorithmParamItem[]]
  'openAudioSelect': [audioType: 'dry' | 'noise', callback: (audios: { id: string; name?: string }[]) => void]
  'previewAudio': [audioId: string]
}>()

const audioConfig = inject<any>('audioConfig', {})

// 当前轮的算法参数：优先从独立列 roundAlgorithmParams 读取，兼容回退到 round.algorithmParams
const currentAlgoParams = computed<AlgorithmParamItem[]>(() => {
  if (props.roundAlgorithmParams && props.roundAlgorithmParams.length > 0) {
    return props.roundAlgorithmParams
  }
  // 兼容回退：子组件编辑期间可能仍写入 round.algorithmParams
  return (props.round.algorithmParams as AlgorithmParamItem[]) || []
})

// 算法参数更新：同时通知独立列和 round（兼容）
function onAlgoParamsUpdate(params: AlgorithmParamItem[]) {
  emit('update:round-algo-params', params)
  emit('update:round', { ...props.round, algorithmParams: params })
}

function getAudioName(audioId: string): string {
  return audioConfig?.getAudioName?.(audioId) || audioId
}

function getAudioTags(audioId: string): string {
  return audioConfig?.getAudioTags?.(audioId) || ''
}

function getAudioDuration(audioId: string): number {
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

function getAlgoParam(fieldCode: string, defaultValue?: unknown): unknown {
  const params = currentAlgoParams.value
  const item = params.find((p) => p.field_code === fieldCode)
  return item?.field_value ?? defaultValue ?? ''
}

function setAlgoParam(fieldCode: string, value: unknown) {
  const params = [...currentAlgoParams.value]
  const idx = params.findIndex((p) => p.field_code === fieldCode)
  if (idx >= 0) {
    params[idx] = { field_code: fieldCode, field_value: value }
  } else {
    params.push({ field_code: fieldCode, field_value: value })
  }
  onAlgoParamsUpdate(params)
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

function addNoise() {
  emit('openAudioSelect', 'noise', (audios: { id: string; name?: string }[]) => {
    if (audios.length > 0) {
      updateNoise('audioId', audios[0].id)
    }
  })
}

function previewNoise() {
  const audioId = props.round.backgroundNoise?.audioId
  if (audioId) {
    emit('previewAudio', audioId)
  }
}

function openNoiseAudioModal() {
  emit('openAudioSelect', 'noise', (audios: { id: string; name?: string }[]) => {
    if (audios.length > 0) {
      updateNoise('audioId', audios[0].id)
    }
  })
}

// ---- 兼容文件名/设备名格式的显示 ----
// 是否有噪声音频（audioId 或 audioName 或 audio 文件名）
const hasNoiseAudio = computed(() => {
  const bg = props.round.backgroundNoise
  if (!bg) return false
  return !!(bg as any).audioId || !!(bg as any).audioName || !!(bg as any).audio
})

// 噪声音频显示名：优先 audioId 反查，其次 audioName，最后 audio 文件名
const noiseAudioDisplayName = computed(() => {
  const bg = props.round.backgroundNoise as any
  if (!bg) return ''
  if (bg.audioId) {
    const name = getAudioName(bg.audioId)
    if (name && name !== bg.audioId) return name
  }
  return bg.audioName || bg.audio || '(未选择音频)'
})

// 当前选中的设备 ID 集合（含从设备名反查的）
const noiseDeviceIdSet = computed<Set<string>>(() => {
  const bg = props.round.backgroundNoise as any
  if (!bg) return new Set()
  const ids: string[] = Array.isArray(bg.deviceIds) ? bg.deviceIds.map(String) : []
  // 从设备名反查 ID：deviceNames → playbackDevices.name → id
  const names: string[] = Array.isArray(bg.deviceNames) ? bg.deviceNames : []
  for (const name of names) {
    const dev = props.playbackDevices.find((d: PlaybackDevice) => d.name === name)
    if (dev && !ids.includes(String(dev.id))) ids.push(String(dev.id))
  }
  return new Set(ids)
})

// 未匹配到 ID 的设备名（提示用户）
const unmatchedNoiseDeviceNames = computed<string[]>(() => {
  const bg = props.round.backgroundNoise as any
  if (!bg || !Array.isArray(bg.deviceNames) || bg.deviceNames.length === 0) return []
  return bg.deviceNames.filter((name: string) =>
    !props.playbackDevices.some((d: PlaybackDevice) => d.name === name)
  )
})

function isNoiseDeviceSelected(deviceId: string): boolean {
  return noiseDeviceIdSet.value.has(deviceId)
}

function toggleNoiseDevice(deviceId: string, checked: boolean) {
  const current = new Set(noiseDeviceIdSet.value)
  if (checked) current.add(deviceId)
  else current.delete(deviceId)
  updateNoise('deviceIds', Array.from(current))
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

.rce-noise-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--background-secondary, #f5f5f5);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px 8px 0 0;
  border-bottom: none;
}
.rce-noise-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  display: flex;
  align-items: center;
  gap: 6px;
}
.rce-noise-title i { font-size: 12px; color: var(--text-light, #999); }

.rce-noise-remove-btn {
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
.rce-noise-remove-btn:hover {
  background: var(--danger-color, #f44336);
  color: #fff;
}

.rce-noise-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
  border: 1px dashed #ccc;
  border-radius: 0 0 8px 8px;
  color: #999;
  font-size: 13px;
}

.rce-noise-body {
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 0 0 8px 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 噪声音频卡片 */
.rce-noise-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #e0e7ff;
  border-radius: 6px;
  background: #f8f9ff;
}
.rce-noise-card-info { flex: 1; min-width: 0; }
.rce-noise-card-row { display: flex; align-items: center; gap: 6px; }
.rce-noise-card-icon { color: #6366f1; font-size: 12px; }
.rce-noise-card-name {
  font-size: 13px; font-weight: 500; color: #333;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
}
.rce-noise-card-duration {
  font-size: 11px; color: #999;
  display: flex; align-items: center; gap: 3px; white-space: nowrap;
}
.rce-noise-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.rce-noise-tag {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: #e0e7ff; color: #4f46e5;
}
.rce-noise-card-actions { display: flex; gap: 4px; flex-shrink: 0; }

/* 播放设备多选 */
.rce-noise-devices {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.rce-noise-device-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid #d0d7de;
  border-radius: 16px;
  background: #f6f8fa;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.rce-noise-device-chip input {
  margin: 0;
}
.rce-noise-device-chip:has(input:checked) {
  background: #e6f4ff;
  border-color: #4096ff;
  color: #1677ff;
}
.rce-noise-device-unmatched {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid #ffd591;
  border-radius: 16px;
  background: #fffbe6;
  color: #d48806;
  font-size: 12px;
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
