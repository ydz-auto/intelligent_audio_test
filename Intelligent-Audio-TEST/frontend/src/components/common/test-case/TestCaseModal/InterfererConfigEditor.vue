<template>
  <div class="interferer-editor">
    <div class="intf-header">
      <span class="intf-title">
        <i class="fas fa-user-friends"></i> 干扰人配置
      </span>
      <button type="button" class="btn btn-sm btn-outline-primary" @click="addInterferer">
        <i class="fas fa-plus"></i> 添加干扰人
      </button>
    </div>

    <div v-if="interferers.length === 0" class="intf-empty">
      <i class="fas fa-info-circle"></i>
      未配置干扰人，点击"添加干扰人"开始配置
    </div>

    <div class="intf-list">
      <div
        v-for="(item, index) in interferers"
        :key="index"
        class="intf-card"
      >
        <!-- 卡片头 -->
        <div class="intf-card-header">
          <span class="intf-card-title">干扰人 {{ index + 1 }}</span>
          <button
            type="button"
            class="intf-remove-btn"
            title="删除"
            @click="removeInterferer(index)"
          >
            <i class="fas fa-trash-alt"></i> 删除
          </button>
        </div>
        <!-- 卡片体 -->
        <div class="intf-card-body">
          <!-- 干扰音频 -->
          <div class="intf-field">
            <label class="intf-field-label">干扰音频</label>
            <div class="intf-audio-row">
              <input
                type="text"
                class="form-control form-control-sm intf-audio-input"
                :value="item.audioName || item.audioId"
                placeholder="请选择音频..."
                readonly
                @click="openAudioModal(index)"
              />
              <button
                type="button"
                class="btn btn-sm btn-outline-primary"
                @click="openAudioModal(index)"
              >
                <i class="fas fa-music"></i>
              </button>
            </div>
          </div>

          <!-- 播放设备 -->
          <div class="intf-field">
            <label class="intf-field-label">播放设备</label>
            <select
              class="form-control form-control-sm"
              :value="item.playbackDeviceId || ''"
              @change="updateItem(index, 'playbackDeviceId', ($event.target as HTMLSelectElement).value)"
            >
              <option value="">请选择设备...</option>
              <option
                v-for="dev in playbackDevices"
                :key="dev.id"
                :value="String(dev.id)"
              >{{ dev.name }}</option>
            </select>
          </div>

          <!-- 声压级 -->
          <div class="intf-field">
            <label class="intf-field-label">声压级 (dB)</label>
            <input
              type="number"
              class="form-control form-control-sm"
              :value="item.spl"
              min="40"
              max="100"
              step="1"
              @input="updateItem(index, 'spl', Number(($event.target as HTMLInputElement).value))"
            />
          </div>

          <!-- 开始延迟 -->
          <div class="intf-field">
            <label class="intf-field-label">开始延迟 (秒)</label>
            <input
              type="number"
              class="form-control form-control-sm"
              :value="item.startDelay"
              min="0"
              max="300"
              step="1"
              @input="updateItem(index, 'startDelay', Number(($event.target as HTMLInputElement).value))"
            />
            <span class="intf-hint">相对于本轮开始的延迟时间</span>
          </div>

          <!-- 循环播放 -->
          <div class="intf-field intf-field-row">
            <label class="intf-field-label">循环播放</label>
            <label class="intf-switch">
              <input
                type="checkbox"
                :checked="item.loop"
                @change="updateItem(index, 'loop', ($event.target as HTMLInputElement).checked)"
              />
              <span>开启后持续循环，本轮结束自动停止</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import type { AlgorithmParamItem, InterfererConfigItem } from './types'
import type { PlaybackDevice } from '../../../../shared/types'

const props = defineProps<{
  modelValue: AlgorithmParamItem[]
  fieldCode?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AlgorithmParamItem[]]
  'openAudioModal': [callback: (audioId: string, audioName?: string) => void]
}>()

const playbackDevices = inject<PlaybackDevice[]>('playbackDevices', [])

// ---- algorithmParams 读写 ----
function getParam(fieldCode: string, defaultValue?: unknown): unknown {
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

// ---- 干扰人列表读写 ----
const interferers = computed({
  get: (): InterfererConfigItem[] => {
    const raw = getParam('interferers')
    if (!raw) return []
    if (typeof raw === 'string') {
      try { return JSON.parse(raw) } catch { return [] }
    }
    return raw as InterfererConfigItem[]
  },
  set: (val: InterfererConfigItem[]) => setParam('interferers', val),
})

function addInterferer() {
  const newItem: InterfererConfigItem = {
    audioId: '',
    audioName: '',
    playbackDeviceId: '',
    spl: 70,
    startDelay: 0,
    loop: true,
  }
  interferers.value = [...interferers.value, newItem]
}

function removeInterferer(index: number) {
  interferers.value = interferers.value.filter((_, i) => i !== index)
}

function updateItem(index: number, key: keyof InterfererConfigItem, value: unknown) {
  const list = [...interferers.value]
  list[index] = { ...list[index], [key]: value }
  interferers.value = list
}

function openAudioModal(index: number) {
  emit('openAudioModal', (audioId: string, audioName?: string) => {
    updateItem(index, 'audioId', audioId)
    if (audioName) updateItem(index, 'audioName', audioName)
  })
}
</script>

<style scoped>
.interferer-editor {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.intf-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--background-secondary, #f5f5f5);
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.intf-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  display: flex;
  align-items: center;
  gap: 6px;
}
.intf-title i {
  font-size: 12px;
  color: var(--text-light, #999);
}

.intf-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-light, #999);
  font-size: 13px;
}
.intf-empty i {
  margin-right: 4px;
}

.intf-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.intf-card {
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}
.intf-card:last-child {
  border-bottom: none;
}

.intf-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--background-primary, #fff);
  border-bottom: 1px solid #f0f0f0;
}

.intf-card-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #333);
}

.intf-remove-btn {
  padding: 3px 10px;
  font-size: 11px;
  border: 1px solid #ffcdd2;
  border-radius: 4px;
  background: transparent;
  color: var(--danger-color, #f44336);
  cursor: pointer;
  transition: background 0.15s;
}
.intf-remove-btn:hover {
  background: #ffebee;
}

.intf-card-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.intf-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.intf-field-row {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

.intf-field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #666);
  min-width: 80px;
}

.intf-audio-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.intf-audio-input {
  flex: 1;
  cursor: pointer;
  background: var(--background-primary, #fff) !important;
}

.intf-hint {
  font-size: 11px;
  color: var(--text-light, #999);
  margin-top: 1px;
}

.intf-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary, #666);
}
.intf-switch input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary-color, #ff6a00);
}
</style>
