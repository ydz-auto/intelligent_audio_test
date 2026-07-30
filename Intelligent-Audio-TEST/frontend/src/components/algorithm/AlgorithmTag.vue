<template>
  <div class="algorithm-tags">
    <span 
      v-for="algo in displayAlgorithms" 
      :key="algo" 
      class="algorithm-tag"
      :class="`algorithm-tag--${getAlgorithmClass(algo)}`"
    >
      {{ getAlgorithmName(algo) }}
    </span>
    <span 
      v-if="showMore && algorithms && algorithms.length > maxDisplay" 
      class="algorithm-tag algorithm-tag--more"
    >
      +{{ algorithms.length - maxDisplay }}
    </span>
    <span v-if="!algorithms || algorithms.length === 0" class="algorithm-tag algorithm-tag--none">
      未配置
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAlgorithmLabels } from '../../composables/algorithm/useAlgorithmLabels'

const { loadAlgorithms, getAlgorithmLabel, algorithms } = useAlgorithmLabels()

onMounted(() => {
  loadAlgorithms()
})

const props = withDefaults(defineProps<{
  algorithms?: string[]
  maxDisplay?: number
  showMore?: boolean
}>(), {
  algorithms: () => [],
  maxDisplay: 4,
  showMore: true
})

const algorithmLabels: Record<string, string> = {
  'translation': '翻译',
  'asr': 'ASR',
  'speaker_recognition': '说话人',
  'tts': 'TTS',
  'speaker_verification': '声纹验证',
  'speaker_identification': '说话人'
}

const displayAlgorithms = computed(() => {
  if (!props.algorithms || props.algorithms.length === 0) return []
  return props.algorithms.slice(0, props.maxDisplay)
})

const getAlgorithmName = (algo: string): string => {
  if (algorithms.value.length > 0) {
    const found = algorithms.value.find(a => a.value === algo)
    if (found) return found.label
  }
  return algorithmLabels[algo] || algo
}

const getAlgorithmClass = (algo: string): string => {
  const classMap: Record<string, string> = {
    'translation': 'translation',
    'asr': 'asr',
    'speaker_recognition': 'speaker',
    'tts': 'tts',
    'speaker_verification': 'speaker',
    'speaker_identification': 'speaker'
  }
  return classMap[algo] || 'default'
}
</script>

<style scoped>
.algorithm-tags {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.algorithm-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.algorithm-tag--translation {
  background-color: #e3f2fd;
  color: #1565c0;
}

.algorithm-tag--asr {
  background-color: #e8f5e9;
  color: #2e7d32;
}

.algorithm-tag--speaker {
  background-color: #fff3e0;
  color: #e65100;
}

.algorithm-tag--tts {
  background-color: #f3e5f5;
  color: #7b1fa2;
}

.algorithm-tag--default {
  background-color: #f5f5f5;
  color: #616161;
}

.algorithm-tag--more {
  background-color: #e0e0e0;
  color: #424242;
}

.algorithm-tag--none {
  background-color: #fafafa;
  color: #9e9e9e;
  font-style: italic;
}
</style>
