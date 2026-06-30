<template>
  <div class="rce-step" id="step-audio">
    <div class="rce-step-header">
      <i class="fas fa-music rce-step-icon"></i>
      <span class="rce-step-title">音频列表</span>
      <span class="rce-tag rce-tag-gray">round.audios</span>
      <span class="rce-audio-count" v-if="audios.length > 0">共 {{ audios.length }} 条 / 总时长 {{ formatDuration(totalDuration) }}</span>
    </div>

    <!-- 工具栏 -->
    <div class="rce-toolbar" v-if="audios.length > 0">
      <button type="button" class="rce-tool-btn" @click="sortByFileName('asc')" title="按文件名升序">
        <i class="fas fa-sort-alpha-down"></i> 升序
      </button>
      <button type="button" class="rce-tool-btn" @click="sortByFileName('desc')" title="按文件名降序">
        <i class="fas fa-sort-alpha-up"></i> 降序
      </button>
      <button type="button" class="rce-tool-btn" @click="shuffleAudioConfigs" title="随机排序">
        <i class="fas fa-random"></i> 随机
      </button>
      <span class="rce-tool-divider"></span>
      <button type="button" class="rce-tool-btn" @click="toggleTagSelector" title="按标签交错排列">
        <i class="fas fa-tags"></i> 标签交错
      </button>
      <button type="button" class="rce-tool-btn" @click="toggleTagDeviceSelector" title="按标签分配设备">
        <i class="fas fa-tag"></i> 标签设备
      </button>
      <span class="rce-tool-divider"></span>
      <button type="button" class="rce-tool-btn" @click="$emit('openBatchDeviceModal')" title="批量设置播放设备">
        <i class="fas fa-desktop"></i> 批量设备
      </button>
      <button type="button" class="rce-tool-btn" @click="$emit('openCrossDeviceModal')" title="设备交叉分配">
        <i class="fas fa-random"></i> 设备交叉
      </button>
      <button type="button" class="rce-tool-btn" @click="$emit('openBatchSplModal')" title="批量设置声压级">
        <i class="fas fa-volume-up"></i> 批量声压
      </button>
      <span class="rce-tool-divider"></span>
      <button type="button" class="rce-tool-btn rce-tool-btn-danger" @click="clearAllAudioConfigs" title="清空所有">
        <i class="fas fa-trash"></i> 清空
      </button>
    </div>

    <!-- 标签交错选择面板 -->
    <div class="rce-tag-selector-panel" v-if="showTagSelector && uniqueTags.length > 0">
      <div class="rce-tag-selector-hint">选择 2 个以上标签进行交错排列：</div>
      <div class="rce-tag-selector-list">
        <span
          v-for="tag in uniqueTags"
          :key="tag"
          class="rce-tag-chip"
          :class="{ 'selected': selectedTagsForInterleave.includes(tag) }"
          @click="toggleTagSelection(tag)"
        >{{ tag }}</span>
      </div>
      <div class="rce-tag-selector-actions">
        <button type="button" class="btn btn-sm btn-primary" @click="interleaveByTags" :disabled="selectedTagsForInterleave.length < 2">
          <i class="fas fa-check"></i> 确定
        </button>
        <button type="button" class="btn btn-sm btn-secondary" @click="toggleTagSelector">
          <i class="fas fa-times"></i> 取消
        </button>
      </div>
    </div>

    <!-- 标签-设备映射面板 -->
    <div class="rce-tag-device-panel" v-if="showTagDeviceSelector && uniqueTags.length > 0">
      <div class="rce-tag-device-hint">为每个标签分配播放设备：</div>
      <div class="rce-tag-device-list">
        <div v-for="tag in uniqueTags" :key="tag" class="rce-tag-device-row">
          <span class="rce-tag-name">{{ tag }}</span>
          <span class="rce-arrow">→</span>
          <select :value="getDeviceForTag(tag)" @change="updateTagDeviceMapping(tag, ($event.target as HTMLSelectElement).value)" class="form-control form-control-sm rce-device-select">
            <option value="">-- 选择设备 --</option>
            <option v-for="dev in playbackDevices" :key="dev.id" :value="String(dev.id)">{{ dev.name }} (通道 {{ dev.channelIndex }})</option>
          </select>
          <span class="rce-audio-count">({{ getTagAudioCount(tag) }}个音频)</span>
        </div>
      </div>
      <div class="rce-tag-selector-actions">
        <button type="button" class="btn btn-sm btn-primary" @click="assignDeviceByTags" :disabled="!hasValidTagDeviceMapping">
          <i class="fas fa-check"></i> 确定
        </button>
        <button type="button" class="btn btn-sm btn-secondary" @click="toggleTagDeviceSelector">
          <i class="fas fa-times"></i> 取消
        </button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="audios.length === 0" class="rce-empty-state">
      <i class="fas fa-music"></i>
      <p>暂无音频配置</p>
      <button type="button" class="btn btn-sm btn-primary" @click="addAudio">
        <i class="fas fa-plus"></i> 添加音频
      </button>
    </div>

    <!-- 音频列表 -->
    <div v-else class="rce-audio-list">
      <div
        v-for="(audio, aidx) in audios"
        :key="aidx"
        class="rce-audio-card"
        :class="{ 'is-dragging': draggedAudioIndex === aidx, 'drag-over': dragOverAudioIndex === aidx }"
        draggable="true"
        @dragstart="handleAudioDragStart(aidx, $event)"
        @dragend="handleAudioDragEnd"
        @dragover="handleAudioDragOver(aidx, $event)"
        @drop="handleAudioDrop(aidx, $event)"
      >
        <div class="rce-audio-card-header">
          <div class="rce-audio-card-left">
            <span class="rce-drag-handle" title="拖动调整顺序">
              <i class="fas fa-grip-vertical"></i>
            </span>
            <span class="rce-audio-index">音频 {{ aidx + 1 }}</span>
            <span class="rce-audio-name" v-if="audio.audioId" :title="getAudioName(audio.audioId)">
              {{ getAudioName(audio.audioId) }}
            </span>
            <span class="rce-audio-duration" v-if="audio.audioId && getAudioDuration(audio.audioId) > 0">
              <i class="fas fa-clock"></i> {{ formatDuration(getAudioDuration(audio.audioId)) }}
            </span>
          </div>
          <div class="rce-audio-card-actions">
            <button type="button" class="rce-icon-btn" @click="copyAudio(aidx)" title="复制">
              <i class="fas fa-copy"></i>
            </button>
            <button type="button" class="rce-icon-btn rce-icon-btn-danger" @click="removeAudio(aidx)" title="删除">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>
        <div class="rce-audio-card-body">
          <div class="rce-field rce-field-full">
            <label class="rce-field-label">音频文件 <span class="rce-required">*</span></label>
            <div class="rce-audio-input">
              <input
                type="text"
                class="form-control form-control-sm"
                :value="audio.audioId ? getAudioName(audio.audioId) : ''"
                placeholder="选择音频..."
                readonly
                @click="openRoundAudioModal(aidx)"
              />
              <button type="button" class="btn btn-sm btn-outline-primary" @click="openRoundAudioModal(aidx)">
                <i class="fas fa-search"></i>
              </button>
              <button v-if="audio.audioId" type="button" class="btn btn-sm btn-outline-secondary" @click="previewAudio(audio.audioId)" title="试听">
                <i class="fas fa-play"></i>
              </button>
            </div>
            <!-- 音频标签 -->
            <div class="rce-audio-tags" v-if="audio.audioId && getAudioTags(audio.audioId)">
              <span class="rce-audio-tags-label">标签：</span>
              <span class="rce-audio-tag" v-for="tag in getNormalizedTags(getAudioTags(audio.audioId))" :key="tag">{{ tag }}</span>
            </div>
          </div>
          <div class="rce-field">
            <label class="rce-field-label">播放设备</label>
            <div class="rce-device-input">
              <select
                class="form-control form-control-sm"
                :value="audio.playbackDeviceId || ''"
                @change="updateAudio(aidx, 'playbackDeviceId', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">请选择...</option>
                <option v-for="dev in playbackDevices" :key="dev.id" :value="String(dev.id)">{{ dev.name }} (通道 {{ dev.channelIndex }})</option>
              </select>
              <button type="button" class="btn btn-sm btn-outline-primary" @click="$emit('openDeviceModal', aidx)" title="选择设备">
                <i class="fas fa-search"></i>
              </button>
            </div>
          </div>
          <div class="rce-field rce-field-sm">
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
import { computed, inject } from 'vue'
import type { RoundConfigItem, AudioConfig } from '../types'
import type { PlaybackDevice } from '../../../../../shared/types'

const props = defineProps<{
  round: RoundConfigItem
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
  'openAudioSelect': [callback: (audios: { id: string; name?: string }[]) => void]
  'openDeviceModal': [audioIndex: number]
  'openBatchDeviceModal': []
  'openCrossDeviceModal': []
  'openBatchSplModal': []
  'previewAudio': [audioId: string]
}>()

// 注入 audioConfig（由 index.vue provide）
const audioConfig = inject<any>('audioConfig', {})

const playbackDevices = computed<PlaybackDevice[]>(() => audioConfig?.playbackDevices?.value || [])

function getAudioDuration(audioId: string | number): number {
  return audioConfig?.getAudioDuration?.(audioId) || 0
}

function formatDuration(seconds: number): string {
  return audioConfig?.formatDuration?.(seconds) || '0s'
}

const totalDuration = computed(() => {
  let total = 0
  audios.value.forEach(config => {
    if (config.audioId) {
      total += getAudioDuration(config.audioId)
    }
  })
  return total
})

// ---- 本地音频列表 ----
const audios = computed<AudioConfig[]>(() => props.round.audios || [])

function emitRound(newAudios: AudioConfig[]) {
  emit('update:round', { ...props.round, audios: newAudios })
}

// ---- 基础操作 ----
function addAudio() {
  const list = [...audios.value]
  list.push({ audioId: '', playbackDeviceId: '', spl: 65, playOrder: list.length })
  emitRound(list)
}

function removeAudio(index: number) {
  const list = audios.value
    .filter((_, i) => i !== index)
    .map((a, i) => ({ ...a, playOrder: i }))
  emitRound(list)
}

function copyAudio(index: number) {
  const source = audios.value[index]
  const list = [...audios.value]
  list.splice(index + 1, 0, { ...source, playOrder: index + 1 })
  list.forEach((a, i) => { a.playOrder = i })
  emitRound(list)
}

function updateAudio(index: number, key: keyof AudioConfig, value: unknown) {
  const list = [...audios.value]
  list[index] = { ...list[index], [key]: value }
  emitRound(list)
}

function clearAllAudioConfigs() {
  if (audios.value.length > 0 && confirm('确定要清空所有音频配置吗？')) {
    emitRound([])
  }
}

// ---- 音频选择 ----
function openRoundAudioModal(index: number) {
  emit('openAudioSelect', 'dry', (selectedAudios: { id: string; name?: string }[]) => {
    if (selectedAudios.length === 0) return
    const list = [...audios.value]
    // 第一个音频填充当前槽位
    list[index] = { ...list[index], audioId: selectedAudios[0].id }
    // 剩余音频追加为新条目
    for (let i = 1; i < selectedAudios.length; i++) {
      list.push({ audioId: selectedAudios[i].id, playbackDeviceId: '', spl: 65, playOrder: list.length })
    }
    // 重新编号 playOrder
    list.forEach((a, i) => { a.playOrder = i })
    emitRound(list)
  })
}

// ---- 试听 ----
function previewAudio(audioId: string) {
  emit('previewAudio', audioId)
}

// ---- 拖拽排序 ----
const draggedAudioIndex = computed(() => audioConfig?.draggedAudioIndex?.value ?? null)
const dragOverAudioIndex = computed(() => audioConfig?.dragOverAudioIndex?.value ?? null)

function handleAudioDragStart(index: number, event: DragEvent) {
  audioConfig?.handleAudioDragStart?.(index, event)
}

function handleAudioDragEnd() {
  audioConfig?.handleAudioDragEnd?.()
}

function handleAudioDragOver(index: number, event: DragEvent) {
  audioConfig?.handleAudioDragOver?.(index, event)
}

function handleAudioDrop(index: number, _event: DragEvent) {
  if (draggedAudioIndex.value === null || draggedAudioIndex.value === index) return
  if (audios.value.length <= 1) return

  const list = [...audios.value]
  const draggedItem = list[draggedAudioIndex.value]
  list.splice(draggedAudioIndex.value, 1)
  list.splice(index, 0, draggedItem)
  list.forEach((a, i) => { a.playOrder = i })
  emitRound(list)

  audioConfig?.handleAudioDragEnd?.()
}

// ---- 排序 ----
function sortByFileName(order: 'asc' | 'desc') {
  if (audios.value.length <= 1) return
  const audioNames: Record<string, string> = {}
  audios.value.forEach(config => {
    if (config.audioId) {
      audioNames[config.audioId] = audioConfig?.getAudioName?.(config.audioId) || ''
    }
  })
  const list = [...audios.value]
  list.sort((a, b) => {
    const nameA = audioNames[a.audioId] || ''
    const nameB = audioNames[b.audioId] || ''
    return order === 'asc' ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA)
  })
  list.forEach((a, i) => { a.playOrder = i })
  emitRound(list)
}

function shuffleAudioConfigs() {
  if (audios.value.length <= 1) return
  const list = [...audios.value]
  for (let i = list.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[list[i], list[j]] = [list[j], list[i]]
  }
  list.forEach((a, i) => { a.playOrder = i })
  emitRound(list)
}

// ---- 标签交错 ----
const showTagSelector = computed(() => audioConfig?.showTagSelector?.value ?? false)
const selectedTagsForInterleave = computed(() => audioConfig?.selectedTagsForInterleave?.value ?? [])

function getAudioName(audioId: string | number): string {
  return audioConfig?.getAudioName?.(audioId) || '未知音频'
}

function getAudioTags(audioId: string | number): string {
  return audioConfig?.getAudioTags?.(audioId) || ''
}

function getNormalizedTags(tagsStr: string): string[] {
  return audioConfig?.getNormalizedTags?.(tagsStr) || []
}

const uniqueTags = computed(() => {
  if (!audios.value.length) return []
  const tagSet = new Set<string>()
  audios.value.forEach(config => {
    if (config.audioId) {
      const tags = getNormalizedTags(getAudioTags(config.audioId))
      tags.forEach(tag => tagSet.add(tag))
    }
  })
  return Array.from(tagSet)
})

function toggleTagSelector() {
  audioConfig?.toggleTagSelector?.()
}

function toggleTagSelection(tag: string) {
  audioConfig?.toggleTagSelection?.(tag)
}

function interleaveByTags() {
  if (audios.value.length <= 1) return
  const selectedTags = [...selectedTagsForInterleave.value]
  if (selectedTags.length < 2) return

  const matchedConfigs: AudioConfig[] = []
  const unmatchedConfigs: AudioConfig[] = []

  audios.value.forEach(config => {
    if (config.audioId) {
      const tags = getNormalizedTags(getAudioTags(config.audioId))
      const hasAnySelectedTag = selectedTags.some(tag => tags.includes(tag))
      if (hasAnySelectedTag) {
        matchedConfigs.push({ ...config })
      } else {
        unmatchedConfigs.push({ ...config })
      }
    } else {
      unmatchedConfigs.push({ ...config })
    }
  })

  if (matchedConfigs.length < 2) return

  const groupedByTag: Record<string, AudioConfig[]> = {}
  selectedTags.forEach(tag => {
    groupedByTag[tag] = matchedConfigs.filter(config => {
      const tags = getNormalizedTags(getAudioTags(config.audioId))
      return tags.includes(tag)
    })
  })

  const maxGroupSize = Math.max(...Object.values(groupedByTag).map(g => g.length))
  const interleaved: AudioConfig[] = []
  const usedIndices = new Set<number>()

  for (let i = 0; i < maxGroupSize; i++) {
    for (const tag of selectedTags) {
      if (i < groupedByTag[tag].length) {
        const config = groupedByTag[tag][i]
        const originalIdx = matchedConfigs.indexOf(config)
        if (!usedIndices.has(originalIdx)) {
          usedIndices.add(originalIdx)
          interleaved.push(config)
        }
      }
    }
  }

  const remainingMatched = matchedConfigs.filter((_, idx) => !usedIndices.has(idx))
  interleaved.push(...remainingMatched)
  interleaved.push(...unmatchedConfigs)

  interleaved.forEach((a, i) => { a.playOrder = i })
  emitRound(interleaved)

  audioConfig?.toggleTagSelector?.()
}

// ---- 标签-设备映射 ----
const showTagDeviceSelector = computed(() => audioConfig?.showTagDeviceSelector?.value ?? false)
const hasValidTagDeviceMapping = computed(() => audioConfig?.hasValidTagDeviceMapping?.value ?? false)

function toggleTagDeviceSelector() {
  audioConfig?.toggleTagDeviceSelector?.()
}

function getDeviceForTag(tag: string): string {
  return audioConfig?.getDeviceForTag?.(tag) || ''
}

function updateTagDeviceMapping(tag: string, deviceId: string) {
  audioConfig?.updateTagDeviceMapping?.(tag, deviceId)
}

function getTagAudioCount(tag: string): number {
  if (!audios.value) return 0
  let count = 0
  audios.value.forEach(config => {
    if (config.audioId) {
      const tags = getNormalizedTags(getAudioTags(config.audioId))
      if (tags.includes(tag)) count++
    }
  })
  return count
}

function assignDeviceByTags() {
  if (!hasValidTagDeviceMapping.value || !audios.value.length) return

  const list = audios.value.map(config => {
    if (config.audioId) {
      const tags = getNormalizedTags(getAudioTags(config.audioId))
      const matchedTag = tags.find(tag => audioConfig?.getDeviceForTag?.(tag))
      if (matchedTag) {
        const deviceId = audioConfig?.getDeviceForTag?.(matchedTag)
        if (deviceId) {
          return { ...config, playbackDeviceId: deviceId }
        }
      }
    }
    return { ...config }
  })
  emitRound(list)
  audioConfig?.toggleTagDeviceSelector?.()
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

.rce-audio-count {
  font-size: 12px;
  color: var(--text-secondary, #666);
  margin-left: auto;
}

/* 工具栏 */
.rce-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  padding: 6px 10px;
  background: var(--background-secondary, #f5f6f8);
  border-radius: 6px;
  flex-wrap: wrap;
}
.rce-tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  background: var(--background-primary, #fff);
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.15s ease;
}
.rce-tool-btn:hover {
  border-color: var(--primary-color, #ff6a00);
  color: var(--primary-color, #ff6a00);
}
.rce-tool-btn-danger:hover {
  border-color: var(--danger-color, #f44336);
  color: var(--danger-color, #f44336);
}
.rce-tool-divider {
  width: 1px;
  height: 18px;
  background: var(--border-color, #e0e0e0);
  margin: 0 4px;
}

/* 标签交错面板 */
.rce-tag-selector-panel,
.rce-tag-device-panel {
  margin-bottom: 10px;
  padding: 10px 12px;
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
}
.rce-tag-selector-hint,
.rce-tag-device-hint {
  font-size: 12px;
  color: var(--text-secondary, #666);
  margin-bottom: 8px;
}
.rce-tag-selector-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.rce-tag-chip {
  padding: 4px 12px;
  font-size: 12px;
  background: var(--secondary-light, #f0f0f0);
  color: var(--text-secondary, #666);
  border-radius: 12px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}
.rce-tag-chip:hover {
  border-color: var(--primary-color, #ff6a00);
}
.rce-tag-chip.selected {
  background: var(--primary-color, #ff6a00);
  color: #fff;
}
.rce-tag-selector-actions {
  display: flex;
  gap: 6px;
}

/* 标签-设备映射 */
.rce-tag-device-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}
.rce-tag-device-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.rce-tag-name {
  min-width: 60px;
  font-weight: 500;
  color: var(--text-primary, #333);
}
.rce-arrow { color: var(--text-light, #999); }
.rce-device-select { flex: 1; max-width: 300px; }

/* 空状态 */
.rce-empty-state {
  text-align: center;
  padding: 30px 20px;
  color: var(--text-secondary, #999);
}
.rce-empty-state i {
  font-size: 36px;
  margin-bottom: 10px;
  opacity: 0.4;
}
.rce-empty-state p {
  margin-bottom: 12px;
  font-size: 13px;
}

/* 音频列表 */
.rce-audio-list { display: flex; flex-direction: column; gap: 8px; }

.rce-audio-card {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.rce-audio-card.is-dragging {
  opacity: 0.5;
  border-style: dashed;
}
.rce-audio-card.drag-over {
  border-color: var(--primary-color, #ff6a00);
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.15);
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
.rce-audio-card-left {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}
.rce-drag-handle {
  cursor: grab;
  color: var(--text-light, #ccc);
  font-size: 12px;
}
.rce-drag-handle:active { cursor: grabbing; }
.rce-audio-index {
  font-weight: 600;
  color: var(--text-secondary, #666);
  white-space: nowrap;
}
.rce-audio-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary, #333);
  font-weight: 400;
}
.rce-audio-card-actions {
  display: flex;
  gap: 4px;
}
.rce-icon-btn {
  width: 24px;
  height: 24px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary, #666);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  transition: all 0.15s ease;
}
.rce-icon-btn:hover {
  border-color: var(--primary-color, #ff6a00);
  color: var(--primary-color, #ff6a00);
}
.rce-icon-btn-danger:hover {
  border-color: var(--danger-color, #f44336);
  color: var(--danger-color, #f44336);
}

.rce-audio-card-body {
  padding: 10px 12px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.rce-field { display: flex; flex-direction: column; gap: 3px; }
.rce-field-full { flex: 1 1 100%; }
.rce-field-sm { max-width: 120px; }
.rce-field-label { font-size: 12px; font-weight: 500; color: var(--text-secondary, #666); }
.rce-required { color: var(--danger-color, #f44336); }

.rce-audio-input { display: flex; gap: 4px; align-items: center; }
.rce-audio-input input {
  flex: 1;
  cursor: pointer;
  background: var(--background-primary, #fff) !important;
}

.rce-audio-tags {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin-top: 4px;
  padding: 4px 6px;
  background: var(--background-secondary, #f9f9f9);
  border-radius: 4px;
  flex-wrap: wrap;
}
.rce-audio-tags-label {
  font-size: 11px;
  color: var(--text-secondary, #999);
  flex-shrink: 0;
}
.rce-audio-tag {
  padding: 1px 8px;
  font-size: 11px;
  background: var(--primary-light, #fff0e6);
  color: var(--primary-color, #ff6a00);
  border-radius: 10px;
}

.rce-add-btn { align-self: flex-start; margin-top: 4px; }

.rce-audio-duration {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  font-size: 11px;
  background: var(--background-secondary, #f0f0f0);
  color: var(--text-secondary, #666);
  border-radius: 10px;
  white-space: nowrap;
}
.rce-audio-duration i {
  font-size: 10px;
  opacity: 0.7;
}

.rce-device-input {
  display: flex;
  gap: 4px;
  align-items: center;
}
.rce-device-input select {
  flex: 1;
}
</style>
