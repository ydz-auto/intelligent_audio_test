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
          <!-- 干扰音频 — 音频卡片样式 -->
          <div class="intf-field">
            <label class="intf-field-label">干扰音频</label>
            <div v-if="item.audioId || item.audioName" class="intf-audio-card">
              <div class="intf-audio-card-info">
                <div class="intf-audio-card-row">
                  <i class="fas fa-music intf-audio-card-icon"></i>
                  <span class="intf-audio-card-name" :title="interfererAudioDisplayName(item)">
                    {{ interfererAudioDisplayName(item) }}
                  </span>
                  <span class="intf-audio-card-duration" v-if="item.audioId && getAudioDuration(item.audioId) > 0">
                    <i class="fas fa-clock"></i> {{ formatDuration(getAudioDuration(item.audioId)) }}
                  </span>
                  <span v-if="!item.audioId && item.audioName" class="intf-audio-card-warn" :title="'导入时未匹配到音频ID，保存后后端会按文件名解析'">
                    <i class="fas fa-exclamation-triangle"></i> 未匹配ID
                  </span>
                </div>
                <div class="intf-audio-card-tags" v-if="item.audioId && getAudioTags(item.audioId)">
                  <span class="intf-audio-tag" v-for="tag in getNormalizedTags(getAudioTags(item.audioId))" :key="tag">{{ tag }}</span>
                </div>
              </div>
              <div class="intf-audio-card-actions">
                <button type="button" class="btn btn-sm btn-outline-primary" @click="openAudioModal(index)">
                  <i class="fas fa-exchange-alt"></i> 更换
                </button>
                <button type="button" class="btn btn-sm btn-outline-info" v-if="item.audioId" @click="previewAudio(item.audioId)">
                  <i class="fas fa-play"></i> 试听
                </button>
                <button type="button" class="btn btn-sm btn-outline-danger" @click="updateItem(index, 'audioId', ''); updateItem(index, 'audioName', '')">
                  <i class="fas fa-times"></i>
                </button>
              </div>
            </div>
            <div v-else class="intf-audio-empty" @click="openAudioModal(index)">
              <i class="fas fa-plus-circle"></i>
              <span>选择干扰音频</span>
            </div>
          </div>

          <!-- 播放设备 -->
          <div class="intf-field">
            <label class="intf-field-label">播放设备</label>
            <select
              class="form-control form-control-sm"
              :value="interfererDeviceSelectedValue(item)"
              @change="onInterfererDeviceChange(index, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">请选择设备...</option>
              <option
                v-for="dev in playbackDevices"
                :key="dev.id"
                :value="String(dev.id)"
              >{{ dev.name }}</option>
            </select>
            <span v-if="!item.playbackDeviceId && item.playbackDeviceName" class="intf-hint">
              <i class="fas fa-exclamation-triangle"></i> 导入设备名"{{ item.playbackDeviceName }}"未匹配到ID
            </span>
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
  'previewAudio': [audioId: string]
}>()

// inject audioConfig 和 playback devices
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
// 兼容三种存储格式：
// - 嵌套结构（{audio:{id,name}, device:{id}, startDelay, ...}）
// - 扁平 camelCase（{audioId, audioName, playbackDeviceId, startDelay, ...}）
// - 扁平 snake_case（{audio_id, audio_name, playback_device_id, start_delay, ...}）
// - 扁平名称（统一标注文件导入：{audio:"文件名.wav", playback_device_name:"设备名", spl, ...}）
function normalizeInterfererItem(item: any): InterfererConfigItem {
  if (!item || typeof item !== 'object') return {
    audioId: '', audioName: '', playbackDeviceId: '', playbackDeviceName: '', spl: 70, startDelay: 0, loop: true,
  }
  // 嵌套结构
  const audioId = item.audio?.id ?? item.audioId ?? item.audio_id ?? ''
  // 兼容 audio 为文件名字符串（统一标注文件格式）
  const audioName = item.audio?.name ?? item.audioName ?? item.audio_name ?? (typeof item.audio === 'string' ? item.audio : '')
  const playbackDeviceId = item.device?.id ?? item.playbackDeviceId ?? item.playback_device_id ?? ''
  // 兼容 playback_device_name（设备名，统一标注文件格式）
  const playbackDeviceName = item.device?.name ?? item.playbackDeviceName ?? item.playback_device_name ?? ''
  return {
    audioId: String(audioId),
    audioName: String(audioName),
    playbackDeviceId: String(playbackDeviceId),
    playbackDeviceName: String(playbackDeviceName),
    spl: item.spl ?? 70,
    startDelay: item.startDelay ?? item.start_delay ?? 0,
    loop: item.loop ?? true,
  }
}

const interferers = computed({
  get: (): InterfererConfigItem[] => {
    const raw = getParam('interferers')
    if (!raw) return []
    let list: any[] = []
    if (typeof raw === 'string') {
      try { list = JSON.parse(raw) } catch { return [] }
    } else if (Array.isArray(raw)) {
      list = raw
    } else {
      return []
    }
    return list.map(normalizeInterfererItem)
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

// 干扰人音频显示名：优先 audioId 反查，其次 audioName，兜底提示
function interfererAudioDisplayName(item: InterfererConfigItem): string {
  if (item.audioId) {
    const name = getAudioName(item.audioId)
    if (name && name !== item.audioId) return name
  }
  return item.audioName || '(未选择音频)'
}

// 干扰人设备 select 的选中值：优先 playbackDeviceId，其次从设备名反查
function interfererDeviceSelectedValue(item: InterfererConfigItem): string {
  if (item.playbackDeviceId) return String(item.playbackDeviceId)
  if (item.playbackDeviceName) {
    const dev = playbackDevices.find((d: PlaybackDevice) => d.name === item.playbackDeviceName)
    if (dev) return String(dev.id)
  }
  return ''
}

// 干扰人设备 select change 处理：更新 playbackDeviceId 和 playbackDeviceName
function onInterfererDeviceChange(index: number, deviceId: string) {
  const list = [...interferers.value]
  const dev = deviceId ? playbackDevices.find((d: PlaybackDevice) => String(d.id) === deviceId) : null
  list[index] = {
    ...list[index],
    playbackDeviceId: deviceId,
    playbackDeviceName: dev?.name || '',
  }
  interferers.value = list
}

function openAudioModal(index: number) {
  emit('openAudioModal', (audioId: string, audioName?: string) => {
    updateItem(index, 'audioId', audioId)
    if (audioName) updateItem(index, 'audioName', audioName)
  })
}

function previewAudio(audioId: string) {
  emit('previewAudio', audioId)
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

/* 音频卡片样式 */
.intf-audio-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #e0e7ff;
  border-radius: 6px;
  background: #f8f9ff;
}
.intf-audio-card-info {
  flex: 1;
  min-width: 0;
}
.intf-audio-card-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.intf-audio-card-icon {
  color: #6366f1;
  font-size: 12px;
}
.intf-audio-card-name {
  font-size: 13px;
  font-weight: 500;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.intf-audio-card-duration {
  font-size: 11px;
  color: #999;
  display: flex;
  align-items: center;
  gap: 3px;
}
.intf-audio-card-warn {
  font-size: 11px;
  color: #d48806;
  display: flex;
  align-items: center;
  gap: 3px;
}
.intf-audio-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.intf-audio-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: #e0e7ff;
  color: #4f46e5;
}
.intf-audio-card-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.intf-audio-empty {
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
.intf-audio-empty:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #f8f9ff;
}
</style>
