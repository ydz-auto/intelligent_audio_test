<template>
  <div class="algorithm-selection">
    <div v-if="filteredAlgorithmList.length === 0" class="empty-state">
      <i class="fas fa-inbox empty-icon"></i>
      <p>暂无可用算法，请先配置算法</p>
    </div>

    <div v-else class="algorithm-grid">
      <div
        v-for="algo in filteredAlgorithmList"
        :key="algo.value"
        class="algorithm-card"
        :class="{ selected: selectedAlgorithmType === algo.value }"
        @click="handleSelectAlgorithm(algo.value)"
      >
        <div class="algorithm-card-header">
          <div class="card-info">
            <span class="algorithm-icon"><i :class="['fas', getAlgorithmIcon(algo.group_name)]"></i></span>
            <div class="algorithm-name">{{ algo.name }}</div>
          </div>
          <div class="card-actions">
            <button class="btn-icon-only" title="算法配置" @click.stop="$emit('open-config', algo)">
              <i class="fas fa-cog"></i>
            </button>
          </div>
        </div>
        <div class="card-content">
          <div class="algorithm-meta">
            <div class="algorithm-meta-item">
              <span class="algorithm-meta-label">分组:</span>
              <span class="algorithm-meta-value">{{ algo.group_name || '未分组' }}</span>
            </div>
          </div>
        </div>
        <div class="algorithm-card-footer">
          <input
            type="checkbox"
            :id="`algo-${algo.value}`"
            class="algorithm-checkbox"
            :checked="selectedAlgorithmType === algo.value"
            @click.stop
            @change="handleSelectAlgorithm(algo.value)"
          >
          <label
            class="algorithm-select-btn"
            @click.stop="handleSelectAlgorithm(algo.value)"
          >
            {{ selectedAlgorithmType === algo.value ? '已选择' : '选择' }}
          </label>
        </div>
      </div>
    </div>

    <div v-if="selectedAlgorithmType" class="selected-info">
      <span class="selected-label">当前选择：{{ getAlgorithmName(selectedAlgorithmType) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AlgorithmOption } from '@/composables/algorithm/useAlgorithmSelection'

interface Props {
  algorithmList: AlgorithmOption[]
  selectedAlgorithmType: string | null
  searchQuery: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', type: string): void
  (e: 'open-config', algo: AlgorithmOption): void
  (e: 'update:searchQuery', value: string): void
}>()

const filteredAlgorithmList = computed(() => {
  if (!props.searchQuery.trim()) {
    return props.algorithmList
  }
  const query = props.searchQuery.toLowerCase().trim()
  return props.algorithmList.filter(algo =>
    algo.name?.toLowerCase().includes(query) ||
    algo.group_name?.toLowerCase().includes(query) ||
    algo.value?.toLowerCase().includes(query)
  )
})

function handleSelectAlgorithm(type: string) {
  emit('select', type)
}

function getAlgorithmName(type: string): string {
  const algo = props.algorithmList.find(a => a.value === type)
  return algo?.name || type || '未知算法'
}

function getAlgorithmIcon(groupName?: string): string {
  const iconMap: Record<string, string> = {
    '翻译': 'fa-globe',
    '语音识别': 'fa-microphone',
    '声纹识别': 'fa-user',
    '语音合成': 'fa-volume-up',
    'asr': 'fa-microphone',
    'tts': 'fa-volume-up',
    'nlu': 'fa-brain',
    'speaker_recognition': 'fa-user',
    'speaker_verification': 'fa-check-circle',
    'speaker_identification': 'fa-search',
    'asr_eval': 'fa-chart-bar',
    'translation': 'fa-globe',
    'general': 'fa-cog'
  }
  return iconMap[groupName || ''] || 'fa-cog'
}
</script>

<style>
</style>