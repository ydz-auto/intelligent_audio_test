<template>
  <div class="audio-timeline-viz">
    <div class="timeline-header">
      <div class="timeline-title">
        <i class="fas fa-wave-square"></i>
        <span>音频时间轴</span>
      </div>
      <div class="timeline-controls">
        <div class="zoom-controls">
          <button @click="zoomOut" class="zoom-btn" title="缩小">
            <i class="fas fa-search-minus"></i>
          </button>
          <span class="zoom-level">{{ scale.toFixed(1) }}x</span>
          <button @click="zoomIn" class="zoom-btn" title="放大">
            <i class="fas fa-search-plus"></i>
          </button>
          <button @click="resetZoom" class="zoom-btn" title="重置">
            <i class="fas fa-undo"></i>
          </button>
        </div>
      </div>
    </div>

    <div class="timeline-content" v-if="hasTimelineData" @wheel.prevent="handleWheelZoom">
      <div class="timeline-track">
        <div class="track-labels">
          <div class="track-label">音频</div>
        </div>
        <div class="track-container">
          <div
            v-for="(audio, idx) in audioList"
            :key="audio.id || `audio-${idx}`"
            class="audio-segment"
            :class="getAudioClass(audio)"
            :style="getSegmentStyle(audio)"
            @click="playAudio(audio, idx)"
            :title="getAudioTooltip(audio)"
          >
            <div class="segment-content">
              <i class="fas fa-play-circle segment-icon"></i>
              <span class="segment-label">{{ getAudioLabel(audio) }}</span>
            </div>
            <div class="segment-time">
              {{ formatTime(audio.timelineStart) }} - {{ formatTime(audio.timelineEnd) }}
            </div>
          </div>
        </div>
      </div>

      <div class="timeline-scale">
        <span class="scale-start">0s</span>
        <div class="scale-bar">
          <div
            v-for="(tick, idx) in timeTicks"
            :key="idx"
            class="scale-tick"
            :style="{ left: tick.percent + '%' }"
          >
            <span class="tick-label">{{ tick.label }}</span>
          </div>
        </div>
        <span class="scale-end">{{ formatTime(totalDuration) }}</span>
      </div>

      <div class="audio-legend">
        <div class="legend-item api">
          <span class="legend-color"></span>
          <span>API测试音频</span>
        </div>
        <div class="legend-item e2e">
          <span class="legend-color"></span>
          <span>E2E测试音频</span>
        </div>
        <div class="legend-item noise">
          <span class="legend-color"></span>
          <span>噪声</span>
        </div>
      </div>
    </div>

    <div class="timeline-empty" v-else>
      <i class="fas fa-music"></i>
      <span>暂无音频数据</span>
    </div>

    <AudioPlayerModal
      v-if="showAudioModal && currentPlayingAudio"
      :visible="showAudioModal"
      :audioId="currentPlayingAudio.id"
      :audioTitle="currentPlayingAudio.label || '音频播放'"
      :audioType="currentPlayingAudio.type || currentPlayingAudio.testType || 'api'"
      :spl="currentPlayingAudio.spl"
      :offset="currentPlayingAudio.offset"
      @close="closeAudioModal"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import AudioPlayerModal from './AudioPlayerModal.vue';

const props = defineProps({
  audioList: {
    type: Array,
    default: () => []
  }
});

const scale = ref(1);
const showAudioModal = ref(false);
const currentPlayingAudio = ref(null);

const hasTimelineData = computed(() => {
  return props.audioList && props.audioList.length > 0;
});

const totalDuration = computed(() => {
  if (!props.audioList || props.audioList.length === 0) return 10;
  const maxEnd = Math.max(...props.audioList.map(a => a.timelineEnd || a.duration || 0));
  return Math.ceil(maxEnd) || 10;
});

const effectiveDuration = computed(() => {
  return totalDuration.value / scale.value;
});

const timeTicks = computed(() => {
  const duration = effectiveDuration.value;
  const ticks = [];
  const interval = duration <= 10 ? 2 : (duration <= 30 ? 5 : 10);
  for (let i = 0; i <= duration; i += interval) {
    ticks.push({
      label: `${i}s`,
      percent: (i / duration) * 100
    });
  }
  return ticks;
});

const getAudioClass = (audio) => {
  const type = audio.testType || audio.type || audio.audio_type || 'api';
  if (type === 'noise') return 'noise-segment';
  if (type === 'e2e') return 'e2e-segment';
  return 'api-segment';
};

const getSegmentStyle = (audio) => {
  const start = audio.timelineStart || 0;
  const end = audio.timelineEnd || (start + (audio.duration || 1));
  const duration = end - start;
  const maxDur = totalDuration.value / scale.value;

  return {
    left: `${(start / maxDur) * 100}%`,
    width: `${Math.max((duration / maxDur) * 100, 5)}%`
  };
};

const getAudioLabel = (audio) => {
  return audio.label || audio.filename || `音频 ${audio.id || ''}`;
};

const getAudioTooltip = (audio) => {
  const lines = [
    `名称: ${audio.filename || audio.label || '未知'}`,
    `时间: ${formatTime(audio.timelineStart)} - ${formatTime(audio.timelineEnd)}`,
    `时长: ${formatDuration(audio.duration)}`,
  ];
  if (audio.spl) lines.push(`声压级: ${audio.spl}dB`);
  if (audio.playOrder !== undefined && audio.playOrder !== null) lines.push(`播放顺序: ${audio.playOrder}`);
  if (audio.playbackDeviceName || audio.device_name) lines.push(`设备: ${audio.playbackDeviceName || audio.device_name}`);
  return lines.join('\n');
};

const formatTime = (seconds) => {
  if (seconds === undefined || seconds === null) return '0.0';
  return seconds.toFixed(1);
};

const formatDuration = (seconds) => {
  if (!seconds) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const handleWheelZoom = (event) => {
  const delta = event.deltaY > 0 ? -0.2 : 0.2;
  scale.value = Math.max(0.5, Math.min(5, scale.value + delta));
};

const zoomIn = () => {
  scale.value = Math.min(5, scale.value + 0.2);
};

const zoomOut = () => {
  scale.value = Math.max(0.5, scale.value - 0.2);
};

const resetZoom = () => {
  scale.value = 1;
};

const playAudio = (audio, index) => {
  currentPlayingAudio.value = { ...audio, index };
  showAudioModal.value = true;
};

const closeAudioModal = () => {
  showAudioModal.value = false;
  currentPlayingAudio.value = null;
};
</script>

<style scoped>
.audio-timeline-viz {
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.timeline-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.timeline-title i {
  color: #1890ff;
}

.timeline-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.zoom-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.zoom-btn {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.zoom-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.zoom-level {
  font-size: 13px;
  color: #666;
  min-width: 40px;
  text-align: center;
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.timeline-track {
  display: flex;
  gap: 12px;
}

.track-labels {
  width: 60px;
  flex-shrink: 0;
}

.track-label {
  font-size: 12px;
  font-weight: 500;
  color: #888;
  height: 48px;
  display: flex;
  align-items: center;
}

.track-container {
  flex: 1;
  position: relative;
  height: 48px;
  background: #f5f5f5;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
  overflow: hidden;
}

.audio-segment {
  position: absolute;
  height: 40px;
  top: 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 8px;
  overflow: hidden;
}

.audio-segment:hover {
  transform: scaleY(1.1);
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.api-segment {
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  border: 1px solid #91d5ff;
}

.api-segment:hover {
  border-color: #1890ff;
}

.e2e-segment {
  background: linear-gradient(135deg, #f9f0ff 0%, #efdbff 100%);
  border: 1px solid #d3adf7;
}

.e2e-segment:hover {
  border-color: #722ed1;
}

.noise-segment {
  background: linear-gradient(135deg, #fff7e6 0%, #ffe58f 100%);
  border: 1px solid #ffc069;
}

.noise-segment:hover {
  border-color: #fa8c16;
}

.segment-content {
  display: flex;
  align-items: center;
  gap: 6px;
}

.segment-icon {
  font-size: 12px;
  opacity: 0.7;
}

.segment-label {
  font-size: 11px;
  font-weight: 500;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.segment-time {
  font-size: 10px;
  color: #666;
  margin-top: 2px;
}

.timeline-scale {
  display: flex;
  align-items: center;
  padding: 8px 0;
  padding-left: 72px;
  font-size: 12px;
  color: #888;
}

.scale-start,
.scale-end {
  flex-shrink: 0;
  width: 40px;
}

.scale-bar {
  flex: 1;
  position: relative;
  height: 20px;
  border-bottom: 1px solid #d9d9d9;
}

.scale-tick {
  position: absolute;
  bottom: 0;
  transform: translateX(-50%);
}

.tick-label {
  font-size: 10px;
  color: #888;
}

.audio-legend {
  display: flex;
  justify-content: center;
  gap: 24px;
  padding-top: 8px;
  border-top: 1px solid #e8e8e8;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #666;
}

.legend-color {
  width: 16px;
  height: 12px;
  border-radius: 2px;
}

.legend-item.api .legend-color {
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  border: 1px solid #91d5ff;
}

.legend-item.e2e .legend-color {
  background: linear-gradient(135deg, #f9f0ff 0%, #efdbff 100%);
  border: 1px solid #d3adf7;
}

.legend-item.noise .legend-color {
  background: linear-gradient(135deg, #fff7e6 0%, #ffe58f 100%);
  border: 1px solid #ffc069;
}

.timeline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #999;
}

.timeline-empty i {
  font-size: 32px;
  margin-bottom: 8px;
  color: #d9d9d9;
}
</style>
