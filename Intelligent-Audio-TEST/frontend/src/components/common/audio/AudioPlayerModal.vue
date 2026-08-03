<template>
  <teleport to="body" v-if="visible">
    <div class="modal-overlay">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button type="button" class="modal-close" @click="() => handleClose()">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <!-- 错误提示 -->
          <div v-if="playError" class="error-message">
            <i class="fas fa-exclamation-circle"></i>
            <span>{{ playError }}</span>
            <button class="error-dismiss" @click="playError = ''">
              <i class="fas fa-times"></i>
            </button>
          </div>
          
          <div class="audio-info">
            <div class="audio-title">{{ audioTitle  }}</div>
            <div class="audio-type">{{ audioTypeLabel }}</div>
          </div>
          
          <div class="audio-player">
          <div class="progress-bar-container" 
               @mousedown="startDrag"
               @click="updateProgressOnClick">
            <div class="progress-bar" :style="{ width: progressPercentage + '%' }"></div>
          </div>
          <div class="time-info">
            <div class="time-display time-current">{{ formatTime(currentTime) }}</div>
            <div class="time-display time-total">{{ formatTime(duration) }}</div>
          </div>
            
            <div class="controls">
              <button type="button" class="control-btn" @click="togglePlay" :disabled="!audioLoaded">
                <i class="fas" :class="isPlaying ? 'fa-pause' : 'fa-play'"></i>
                {{ isPlaying ? '暂停' : '播放' }}
              </button>
              <button type="button" class="control-btn" @click="stop" :disabled="!audioLoaded">
                <i class="fas fa-stop"></i> 停止
              </button>
              <button type="button" class="control-btn" @click="handleClose">
                <i class="fas fa-times"></i> 关闭
              </button>
            </div>
          </div>
          
          <div class="device-info" v-if="selectedDevices.length > 0">
            <h5>播放设备</h5>
            <ul class="device-list">
              <li v-for="(device, index) in selectedDevices" :key="index" class="device-item">
                <i class="fas fa-check-circle device-status online"></i>
                <span class="device-name">{{ device?.name || '未知设备' }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import type { PlaybackDevice } from '../../../shared/types';
import { useAudioPlayerModal } from './AudioPlayerModal';

interface Props {
  visible: boolean;
  title?: string;
  audioId?: string | number | null;
  audioTitle?: string;
  audioType?: string;
  selectedDevices?: PlaybackDevice[];
  isTestCasePreview?: boolean;
  modalId?: string;
  playbackMode?: string;
  spl?: number | null;
  offset?: number | null;
  playbackDevices?: any[];
  selectedPlaybackDevices?: any[];
}

const props = withDefaults(defineProps<Props>(), {
  title: '音频播放',
  audioId: null,
  audioTitle: '未知音频',
  audioType: 'dry',
  selectedDevices: () => [],
  isTestCasePreview: false,
  modalId: '',
  playbackMode: 'frontend',
  spl: null,
  offset: null,
  playbackDevices: () => [],
  selectedPlaybackDevices: () => []
});

const emit = defineEmits(['close', 'play', 'pause', 'stop', 'confirm', 'cancel', 'save']);

const {
  isPlaying,
  currentTime,
  duration,
  progressPercentage,
  audioLoaded,
  isDragging,
  playError,
  audioTypeLabel,
  formatTime,
  togglePlay,
  stop,
  handleClose,
  startDrag,
  updateProgressOnClick
} = useAudioPlayerModal(props, emit)
</script>

<style scoped>
@import './AudioPlayerModal.css';
</style>
