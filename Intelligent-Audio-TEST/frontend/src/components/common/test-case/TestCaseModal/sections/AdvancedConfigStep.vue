<template>
  <div class="rce-step" id="step-advanced">
    <div class="rce-step-header">
      <i class="fas fa-cogs rce-step-icon"></i>
      <span class="rce-step-title">高级配置</span>
      <span class="rce-tag rce-tag-purple">algorithmParams</span>
    </div>

    <div class="rce-section">
      <div class="rce-param-grid">
        <!-- Audio Select Params -->
        <div v-for="param in audioSelectParams" :key="param.paramCode" class="rce-param-item">
          <label class="rce-param-label">{{ param.paramName || param.paramCode }}</label>
          <div class="rce-audio-input-wrapper">
            <div class="rce-audio-input">
              <input
                type="text"
                class="form-control form-control-sm"
                :value="getAudioName(getAlgoParam(param.paramCode))"
                placeholder="选择音频..."
                readonly
                @click="openAudioForParam(param.paramCode)"
              />
              <button
                type="button"
                class="btn btn-sm btn-outline-primary"
                @click="openAudioForParam(param.paramCode)"
                title="选择音频"
              >
                <i class="fas fa-music"></i>
              </button>
              <button
                v-if="getAlgoParam(param.paramCode)"
                type="button"
                class="btn btn-sm btn-outline-secondary"
                @click="previewAudio(getAlgoParam(param.paramCode))"
                title="试听"
              >
                <i class="fas fa-play"></i>
              </button>
            </div>
            <div class="rce-audio-meta" v-if="getAlgoParam(param.paramCode)">
              <span class="rce-audio-duration" v-if="getAudioDuration(getAlgoParam(param.paramCode)) > 0">
                <i class="fas fa-clock"></i> {{ formatDuration(getAudioDuration(getAlgoParam(param.paramCode))) }}
              </span>
              <span class="rce-audio-tags" v-if="getAudioTags(getAlgoParam(param.paramCode))">
                <span class="rce-audio-tag" v-for="tag in getNormalizedTags(getAudioTags(getAlgoParam(param.paramCode)))" :key="tag">{{ tag }}</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Slider Params -->
        <div v-for="param in sliderParams" :key="param.paramCode" class="rce-param-item">
          <label class="rce-param-label">
            {{ param.paramName || param.paramCode }}
            <span v-if="param.unit" class="rce-param-unit">({{ param.unit }})</span>
          </label>
          <div class="rce-slider-field">
            <input
              type="range"
              class="rce-slider-input"
              :value="getAlgoParam(param.paramCode, param.defaultValue)"
              :min="param.min ?? 0"
              :max="param.max ?? 100"
              :step="param.step ?? 1"
              @input="setAlgoParam(param.paramCode, Number(($event.target as HTMLInputElement).value))"
            />
            <input
              type="number"
              class="form-control form-control-sm rce-slider-number"
              :value="getAlgoParam(param.paramCode, param.defaultValue)"
              :min="param.min ?? 0"
              :max="param.max ?? 100"
              :step="param.step ?? 1"
              @input="setAlgoParam(param.paramCode, Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </div>

        <!-- Switch Params -->
        <div v-for="param in switchParams" :key="param.paramCode" class="rce-param-item">
          <label class="rce-param-label">{{ param.paramName || param.paramCode }}</label>
          <label class="rce-switch-container">
            <input
              type="checkbox"
              :checked="getAlgoParam(param.paramCode, false)"
              @change="setAlgoParam(param.paramCode, ($event.target as HTMLInputElement).checked)"
            />
            <span class="rce-switch-slider"></span>
            <span class="rce-switch-label">{{ getAlgoParam(param.paramCode) ? '启用' : '禁用' }}</span>
          </label>
        </div>

        <!-- Device Select Params -->
        <div v-for="param in deviceSelectParams" :key="param.paramCode" class="rce-param-item">
          <label class="rce-param-label">{{ param.paramName || param.paramCode }}</label>
          <select
            class="form-control form-control-sm"
            :value="String(getAlgoParam(param.paramCode, ''))"
            @change="setAlgoParam(param.paramCode, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">请选择...</option>
            <option v-for="dev in playbackDevices" :key="dev.id" :value="String(dev.id)">
              {{ dev.name }} (通道 {{ dev.channelIndex }})
            </option>
          </select>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import type { RoundConfigItem } from '../types'
import type { PlaybackDevice } from '../../../../../shared/types'

const props = defineProps<{
  round: RoundConfigItem
  caseAlgorithmParams: any[]
  testType: 'api' | 'e2e'
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
  'openAudioSelect': [audioType: 'dry' | 'noise', callback: (audios: { id: string; name?: string }[]) => void]
}>()

const audioConfig = inject<any>('audioConfig', {})
const playbackDevices = computed<PlaybackDevice[]>(() => audioConfig?.playbackDevices?.value || [])

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

function getAudioName(audioId: string | number): string {
  if (!audioId) return ''
  return audioConfig?.getAudioName?.(audioId) || `音频 #${audioId}`
}

function getAudioDuration(audioId: string | number): number {
  return audioConfig?.getAudioDuration?.(audioId) || 0
}

function formatDuration(seconds: number): string {
  return audioConfig?.formatDuration?.(seconds) || '0s'
}

function getAudioTags(audioId: string | number): string {
  return audioConfig?.getAudioTags?.(audioId) || ''
}

function getNormalizedTags(tagsStr: string): string[] {
  return audioConfig?.getNormalizedTags?.(tagsStr) || []
}

function previewAudio(audioId: string | number) {
  audioConfig?.openAudioPreview?.(audioId, 'dry')
}

function openAudioForParam(paramCode: string) {
  emit('openAudioSelect', 'dry', (audios: { id: string; name?: string }[]) => {
    if (audios.length > 0) {
      setAlgoParam(paramCode, audios[0].id)
    }
  })
}

const ADVANCED_TYPES = new Set(['audio_select', 'device_select', 'slider', 'switch'])

const filteredParams = computed(() => {
  const tt = props.testType
  return (props.caseAlgorithmParams || []).filter((p: any) => {
    const scopeMatch = p.scope === 'common' || p.scope === tt || !p.scope
    return scopeMatch && ADVANCED_TYPES.has(p.paramType)
  })
})

const audioSelectParams = computed(() => filteredParams.value.filter((p: any) => p.paramType === 'audio_select'))
const sliderParams = computed(() => filteredParams.value.filter((p: any) => p.paramType === 'slider'))
const switchParams = computed(() => filteredParams.value.filter((p: any) => p.paramType === 'switch'))
const deviceSelectParams = computed(() => filteredParams.value.filter((p: any) => p.paramType === 'device_select'))

const hasAdvancedParams = computed(() => filteredParams.value.length > 0)
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
.rce-tag-purple { background: #f3e8ff; color: #9333ea; }

.rce-section { margin-bottom: 14px; }

.rce-param-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.rce-param-item { flex: 1; min-width: 180px; max-width: 360px; }

.rce-param-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #666);
  margin-bottom: 4px;
}

.rce-param-unit {
  color: var(--text-light, #999);
  font-weight: 400;
}

.rce-audio-input-wrapper {
  width: 100%;
}

.rce-audio-input {
  display: flex;
  gap: 4px;
  align-items: center;
}

.rce-audio-input input {
  flex: 1;
  cursor: pointer;
  background: var(--background-primary, #fff) !important;
}

.rce-audio-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}

.rce-audio-duration {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary, #666);
  background: var(--background-secondary, #f5f5f5);
  border-radius: 10px;
}

.rce-audio-duration i {
  font-size: 10px;
}

.rce-audio-tags {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.rce-audio-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--primary-color, #ff6a00);
  background: var(--primary-light, #fff3e8);
  border-radius: 10px;
  font-weight: 500;
}

.rce-slider-field {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rce-slider-input {
  flex: 1;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: #E5E7EB;
  border-radius: 9999px;
  outline: none;
}

.rce-slider-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  background: #FF6A00;
  border-radius: 50%;
  cursor: pointer;
}

.rce-slider-number {
  width: 80px;
  text-align: center;
  font-weight: 600;
  color: #FF6A00;
}

.rce-switch-container {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  width: auto;
  height: 28px;
  cursor: pointer;
}

.rce-switch-container input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}

.rce-switch-slider {
  position: relative;
  width: 44px;
  height: 22px;
  background-color: #E5E7EB;
  border-radius: 9999px;
  transition: 0.2s ease;
  flex-shrink: 0;
}

.rce-switch-slider::before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  transition: 0.2s ease;
}

.rce-switch-container input:checked + .rce-switch-slider {
  background-color: #FF6A00;
}

.rce-switch-container input:checked + .rce-switch-slider::before {
  transform: translateX(22px);
}

.rce-switch-label {
  font-size: 13px;
  color: var(--text-secondary, #666);
}
</style>
