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
import type { AlgorithmOption } from '@/composables/useAlgorithmSelection'

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
    '语音识别': 'fa-microphone',
    '语音合成': 'fa-volume-up',
    '语音增强': 'fa-headphones',
    '说话人识别': 'fa-user-circle',
    '关键词检测': 'fa-key',
    '情感识别': 'fa-smile',
    '声纹识别': 'fa-fingerprint',
    '语音活动检测': 'fa-wave-square'
  }
  return iconMap[groupName || ''] || 'fa-cogs'
}
</script>

<style scoped>
.algorithm-selection {
  width: 100%;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary, #6b7280);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.algorithm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  padding: 4px;
}

.algorithm-card {
  background: var(--card-bg, #ffffff);
  border: 2px solid var(--border-color, #e5e7eb);
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease-out;
  position: relative;
}

.algorithm-card:hover {
  border-color: var(--primary-color, #3b82f6);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
}

.algorithm-card.selected {
  border-color: var(--primary-color, #3b82f6);
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(59, 130, 246, 0.05) 100%);
}

.algorithm-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.card-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.algorithm-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-color-light, #eff6ff);
  color: var(--primary-color, #3b82f6);
  border-radius: 8px;
  font-size: 16px;
  flex-shrink: 0;
  transition: all 0.2s ease-out;
}

.algorithm-card.selected .algorithm-icon {
  background: var(--primary-color, #3b82f6);
  color: white;
}

.algorithm-name {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary, #1f2937);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.2s ease-out;
}

.algorithm-card.selected .algorithm-name {
  color: var(--primary-color, #3b82f6);
}

.card-actions {
  display: flex;
  gap: 4px;
}

.btn-icon-only {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all 0.2s ease-out;
}

.btn-icon-only:hover {
  background: var(--bg-hover, #f3f4f6);
  color: var(--primary-color, #3b82f6);
}

.card-content {
  margin-bottom: 12px;
}

.algorithm-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.algorithm-meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

.algorithm-meta-label {
  color: var(--text-secondary, #6b7280);
}

.algorithm-meta-value {
  color: var(--text-primary, #1f2937);
}

.algorithm-card-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #e5e7eb);
}

.algorithm-checkbox {
  display: none;
}

.algorithm-select-btn {
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease-out;
  background: var(--bg-secondary, #f3f4f6);
  color: var(--text-primary, #1f2937);
  border: 1px solid var(--border-color, #e5e7eb);
}

.algorithm-select-btn:hover {
  background: var(--primary-color, #3b82f6);
  color: white;
  border-color: var(--primary-color, #3b82f6);
}

.algorithm-card.selected .algorithm-select-btn {
  background: var(--primary-color, #3b82f6);
  color: white;
  border-color: var(--primary-color, #3b82f6);
}

.selected-info {
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--primary-color-light, #eff6ff);
  border-radius: 8px;
  border: 1px solid var(--primary-color, #3b82f6);
}

.selected-label {
  color: var(--primary-color, #3b82f6);
  font-weight: 500;
}
</style>