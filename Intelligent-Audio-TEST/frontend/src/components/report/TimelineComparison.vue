<template>
  <div class="timeline-comparison">
    <div class="timeline-header">
      <div class="timeline-title">
        <i class="fas fa-layer-group"></i>
        <span>时间轴对比</span>
      </div>
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
      <div class="timeline-controls">
        <select
          v-model="selectedResource"
          class="resource-select"
          @change="handleResourceChange"
        >
          <option v-for="res in resources" :key="res" :value="res">
            {{ formatResourceName(res) }}
          </option>
        </select>
        <div class="speaker-filters">
          <label class="speaker-filter-item">
            <input
              type="checkbox"
              :checked="selectedSpeakers.length === 0 || selectedSpeakers.includes('all')"
              @change="toggleAllSpeakers($event)"
            />
            <span>全部</span>
          </label>
          <label
            v-for="spk in speakerList"
            :key="spk"
            class="speaker-filter-item"
          >
            <input
              type="checkbox"
              :value="spk"
              v-model="selectedSpeakers"
            />
            <span>{{ spk }}</span>
          </label>
        </div>
      </div>
    </div>

    <div class="timeline-content" v-if="hasTimelineData" @wheel.prevent="handleWheelZoom"
         :style="{ '--timeline-scale': scale }">
      <div
        v-for="speaker in getFilteredSpeakerList()"
        :key="speaker"
        class="speaker-row"
      >
        <div class="speaker-header">
          <span class="speaker-name">{{ speaker }}</span>
          <span v-if="speakerMapping[speaker]" class="speaker-mapping">
            → {{ speakerMapping[speaker] }}
          </span>
        </div>
        <div class="speaker-timeline">
          <div class="timeline-row reference-row">
            <div class="row-label">参考</div>
            <div class="track-segments">
              <div
                v-for="(seg, idx) in referenceSegmentsBySpeaker[speaker] || []"
                :key="'ref-' + speaker + '-' + idx"
                class="segment reference-segment"
                :style="getSegmentStyle(seg)"
                :title="seg.text"
              >
                <span class="segment-text">{{ seg.text }}</span>
              </div>
              <div v-if="(referenceSegmentsBySpeaker[speaker] || []).length === 0" class="no-segment">
                无数据
              </div>
            </div>
          </div>
          <div class="timeline-row result-row">
            <div class="row-label">结果</div>
            <div class="track-segments">
              <div
                v-for="(seg, idx) in getResultSegmentsForSpeaker(speaker)"
                :key="'res-' + speaker + '-' + idx"
                class="segment result-segment"
                :class="{ 'match-segment': isMatchSegment(speaker, seg) }"
                :style="getSegmentStyle(seg)"
                :title="seg.text"
              >
                <span class="segment-text">{{ seg.text }}</span>
              </div>
              <div v-if="getResultSegmentsForSpeaker(speaker).length === 0" class="no-segment">
                无数据
              </div>
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
        <span class="scale-end">{{ effectiveDuration.toFixed(1) }}s</span>
      </div>
    </div>

    <div class="timeline-empty" v-else>
      <i class="fas fa-chart-line"></i>
      <span>暂无时间轴数据</span>
    </div>
  </div>
</template>

<script setup>
import { useTimelineComparison } from './TimelineComparison'

const props = defineProps({
  algorithmResults: {
    type: Array,
    default: () => []
  },
  referenceParams: {
    type: Object,
    default: () => ({})
  },
  algorithmType: {
    type: String,
    default: ''
  },
  results: {
    type: Array,
    default: () => []
  },
  fieldMapping: {
    type: Object,
    default: () => ({ result: [], reference: [] })
  }
})

const {
  selectedResource,
  selectedSpeakers,
  scale,
  maxDuration,
  effectiveDuration,
  timeTicks,
  resources,
  hasTimelineData,
  speakerList,
  speakerMapping,
  referenceSegmentsBySpeaker,
  getFilteredSpeakerList,
  getSegmentStyle,
  isMatchSegment,
  getResultSegmentsForSpeaker,
  handleResourceChange,
  toggleAllSpeakers,
  handleWheelZoom,
  zoomIn,
  zoomOut,
  resetZoom,
  formatResourceName
} = useTimelineComparison(props)
</script>

<style scoped>
@import './TimelineComparison.css';
</style>
