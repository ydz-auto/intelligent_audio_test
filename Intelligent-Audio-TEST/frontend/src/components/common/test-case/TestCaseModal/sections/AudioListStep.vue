<template>
  <div class="rce-step" id="step-audio">
    <div class="rce-step-header">
      <i class="fas fa-music rce-step-icon"></i>
      <span class="rce-step-title">音频列表</span>
      <span class="rce-tag rce-tag-gray">round.audios</span>
    </div>
    <div class="rce-audio-list">
      <div v-for="(audio, aidx) in (round.audios || [])" :key="aidx" class="rce-audio-card">
        <div class="rce-audio-card-header">
          <span>音频 {{ aidx + 1 }}</span>
          <button type="button" class="rce-remove-btn" @click="removeAudio(aidx)">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="rce-audio-card-body">
          <div class="rce-field">
            <label class="rce-field-label">音频</label>
            <div class="rce-audio-input">
              <input
                type="text"
                class="form-control form-control-sm"
                :value="audio.audioId"
                placeholder="选择音频..."
                readonly
                @click="openRoundAudioModal(aidx)"
              />
              <button type="button" class="btn btn-sm btn-outline-primary" @click="openRoundAudioModal(aidx)">
                <i class="fas fa-music"></i>
              </button>
            </div>
          </div>
          <div class="rce-field">
            <label class="rce-field-label">播放设备</label>
            <select
              class="form-control form-control-sm"
              :value="audio.playbackDeviceId || ''"
              @change="updateAudio(aidx, 'playbackDeviceId', ($event.target as HTMLSelectElement).value)"
            >
              <option value="">请选择...</option>
              <option v-for="dev in playbackDevices" :key="dev.id" :value="String(dev.id)">{{ dev.name }}</option>
            </select>
          </div>
          <div class="rce-field">
            <label class="rce-field-label">声压级 (dB)</label>
            <input
              type="number"
              class="form-control form-control-sm"
              :value="audio.spl ?? 65"
              min="40" max="100" step="1"
              @input="updateAudio(aidx, 'spl', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </div>
      </div>
      <button type="button" class="btn btn-sm btn-outline-primary rce-add-btn" @click="addAudio">
        <i class="fas fa-plus"></i> 添加音频
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject } from 'vue'
import type { RoundConfigItem, AudioConfig } from '../types'
import type { PlaybackDevice } from '../../../../../shared/types'

const props = defineProps<{
  round: RoundConfigItem
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
  'openAudioSelect': [callback: (audioId: string) => void]
}>()

const playbackDevices = inject<PlaybackDevice[]>('playbackDevices', [])

function addAudio() {
  const audios = [...(props.round.audios || [])]
  audios.push({ audioId: '', playbackDeviceId: '', spl: 65, playOrder: audios.length })
  emit('update:round', { ...props.round, audios })
}

function removeAudio(index: number) {
  const audios = props.round.audios.filter((_, i) => i !== index)
    .map((a, i) => ({ ...a, playOrder: i }))
  emit('update:round', { ...props.round, audios })
}

function updateAudio(index: number, key: keyof AudioConfig, value: unknown) {
  const audios = [...(props.round.audios || [])]
  audios[index] = { ...audios[index], [key]: value }
  emit('update:round', { ...props.round, audios })
}

function openRoundAudioModal(index: number) {
  emit('openAudioSelect', (audioId: string) => {
    updateAudio(index, 'audioId', audioId)
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

.rce-audio-list { display: flex; flex-direction: column; gap: 8px; }

.rce-audio-card {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.rce-audio-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--background-secondary, #f5f6f8);
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  font-size: 13px;
  font-weight: 500;
}

.rce-audio-card-body {
  padding: 10px 12px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.rce-field { display: flex; flex-direction: column; gap: 3px; }
.rce-field-label { font-size: 12px; font-weight: 500; color: var(--text-secondary, #666); }

.rce-audio-input { display: flex; gap: 4px; align-items: center; }
.rce-audio-input input {
  flex: 1;
  cursor: pointer;
  background: var(--background-primary, #fff) !important;
}

.rce-remove-btn {
  width: 22px;
  height: 22px;
  border: 1px solid #ffcdd2;
  border-radius: 4px;
  background: transparent;
  color: var(--danger-color, #f44336);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}

.rce-add-btn { align-self: flex-start; margin-top: 4px; }
</style>
