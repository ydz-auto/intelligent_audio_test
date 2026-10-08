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
            <span class="algorithm-icon"><i :class="['fas', getAlgorithmIcon(algo.groupName)]"></i></span>
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
              <span class="algorithm-meta-value">{{ algo.groupName || '未分组' }}</span>
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
<style scoped>

.algorithm-card{
  background: white;
  border-radius: 12px;
  border: 2px solid transparent;
  outline: 1px solid var(--color-slate-200);
  outline-offset: -2px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  transition: border-color 0.2s ease-out, background-color 0.2s ease-out, box-shadow 0.2s ease-out, transform 0.2s ease-out;
  cursor: pointer;
  height: 100%;
  position: relative;
}

.algorithm-card:hover{
  border-color: color-mix(in srgb, var(--primary) 50%, transparent);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary) 15%, transparent);
  transform: translateY(-2px);
}

.algorithm-select-btn{
  flex: 1;
  text-align: center;
  padding: 8px;
  border-radius: 6px;
  background: var(--color-slate-50);
  border: 1px solid var(--color-slate-200);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--transition-fast);
}









/* algorithm-grid - 自全局样式就近迁移 */
.algorithm-grid{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
  margin-top: 20px;
  width: 100%;
}

/* algorithm-card-header - 自全局样式就近迁移 */
.algorithm-card-header{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

/* algorithm-icon - 自全局样式就近迁移 */
.algorithm-icon{
  font-size: 24px;
  line-height: 1;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--color-ant-primary) 10%, transparent) 0%, color-mix(in srgb, var(--color-ant-blue-4) 10%, transparent) 100%);
  border-radius: 10px;
  color: var(--color-ant-primary);
}

/* algorithm-name - 自全局样式就近迁移 */
.algorithm-name{
  font-weight: 600;
  font-size: 16px;
  color: var(--color-legacy-gray-800);
  margin-bottom: 4px;
  transition: color 0.2s ease-out;
}

/* algorithm-meta - 自全局样式就近迁移 */
.algorithm-meta{
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

/* algorithm-meta-item - 自全局样式就近迁移 */
.algorithm-meta-item{
  display: flex;
}

/* algorithm-meta-label - 自全局样式就近迁移 */
.algorithm-meta-label{
  color: var(--color-slate-500);
  width: 60px;
  flex-shrink: 0;
}

/* algorithm-meta-value - 自全局样式就近迁移 */
.algorithm-meta-value{
  color: var(--color-legacy-gray-800);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* algorithm-card-footer - 自全局样式就近迁移 */
.algorithm-card-footer{
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--color-legacy-gray-100);
  display: flex;
  align-items: center;
  gap: 12px;
  transition: border-color 0.2s ease-out;
}

/* selected-info - 自全局样式就近迁移 */
.selected-info{
  margin-top: 20px;
  padding: 16px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--primary) 10%, transparent) 0%, color-mix(in srgb, var(--primary) 10%, transparent) 100%);
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent);
  display: flex;
  align-items: center;
  gap: 12px;
}

/* selected-label - 自全局样式就近迁移 */
.selected-label{
  color: var(--primary-color);
  font-weight: 600;
  font-size: 14px;
}

</style>

<script setup lang="ts">
import { computed } from 'vue'
import type { AlgorithmOption } from '@/domain/model/algorithm'

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
    algo.groupName?.toLowerCase().includes(query) ||
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