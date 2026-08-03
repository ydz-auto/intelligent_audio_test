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
import type { RoundConfigItem } from '../types'
import { useAudioListStep } from './AudioListStep'

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

const {
  audios,
  formatDuration,
  totalDuration,
  sortByFileName,
  shuffleAudioConfigs,
  toggleTagSelector,
  toggleTagDeviceSelector,
  showTagSelector,
  uniqueTags,
  selectedTagsForInterleave,
  toggleTagSelection,
  interleaveByTags,
  showTagDeviceSelector,
  getDeviceForTag,
  updateTagDeviceMapping,
  playbackDevices,
  getTagAudioCount,
  hasValidTagDeviceMapping,
  assignDeviceByTags,
  addAudio,
  draggedAudioIndex,
  dragOverAudioIndex,
  handleAudioDragStart,
  handleAudioDragEnd,
  handleAudioDragOver,
  handleAudioDrop,
  getAudioName,
  getAudioDuration,
  getAudioTags,
  getNormalizedTags,
  copyAudio,
  removeAudio,
  openRoundAudioModal,
  previewAudio,
  updateAudio,
  clearAllAudioConfigs
} = useAudioListStep(props, emit)
</script>

<style scoped>
@import './AudioListStep.css';
</style>
