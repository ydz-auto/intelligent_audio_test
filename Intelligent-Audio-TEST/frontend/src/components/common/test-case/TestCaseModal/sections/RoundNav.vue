<template>
  <div class="rce-round-nav">
    <div class="rce-nav-header">
      <span class="rce-nav-title">轮次列表</span>
      <span class="rce-nav-count">{{ rounds.length }} 轮</span>
    </div>
    <div class="rce-nav-list">
      <div
        v-for="(round, idx) in rounds"
        :key="idx"
        class="rce-nav-item"
        :class="{ active: activeIndex === idx }"
        @click="$emit('update:activeIndex', idx)"
      >
        <span class="rce-nav-num" :class="{ 'has-error': !isRoundValid(round) }">{{ round.roundNumber }}</span>
        <span class="rce-nav-meta">{{ getRoundSummary(round) }}</span>
      </div>
    </div>
    <div class="rce-nav-footer">
      <button type="button" class="rce-nav-btn" @click="$emit('add')">
        <i class="fas fa-plus"></i> 添加轮次
      </button>
      <button
        type="button"
        class="rce-nav-btn"
        :disabled="rounds.length === 0"
        @click="$emit('copy')"
      >
        <i class="fas fa-copy"></i> 复制当前轮次
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RoundConfigItem } from '../types'

defineProps<{
  rounds: RoundConfigItem[]
  activeIndex: number
}>()

defineEmits<{
  'update:activeIndex': [value: number]
  'add': []
  'copy': []
}>()

function isRoundValid(round: RoundConfigItem): boolean {
  const audios = round.audios || []
  return audios.some((a: any) => a.audioId && a.audioId.trim() !== '')
}

function getRoundSummary(round: RoundConfigItem): string {
  const parts: string[] = []
  if (round.audios?.length) parts.push(`${round.audios.length}音频`)
  if (round.evaluation?.dimensions?.length) parts.push(`${round.evaluation.dimensions.length}维度`)
  return parts.join(' · ') || '空轮次'
}
</script>

<style scoped>
.rce-round-nav {
  width: 180px;
  min-width: 180px;
  background: var(--background-secondary, #f5f6f8);
  border-right: 1px solid var(--border-color, #e0e0e0);
  display: flex;
  flex-direction: column;
}

.rce-nav-header {
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.rce-nav-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.rce-nav-count {
  font-size: 11px;
  color: var(--text-light, #999);
  background: var(--background-primary, #fff);
  padding: 2px 8px;
  border-radius: 10px;
}

.rce-nav-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.rce-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 2px;
}
.rce-nav-item:hover {
  background: rgba(0, 0, 0, 0.04);
}
.rce-nav-item.active {
  background: var(--primary-light, #fff3e8);
  color: var(--primary-color, #ff6a00);
}

.rce-nav-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--border-color, #e0e0e0);
  color: var(--text-secondary, #666);
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.rce-nav-item.active .rce-nav-num {
  background: var(--primary-color, #ff6a00);
  color: #fff;
}
.rce-nav-num.has-error {
  background: var(--danger-color, #f44336);
  color: #fff;
}

.rce-nav-meta {
  font-size: 12px;
  color: var(--text-secondary, #666);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rce-nav-item.active .rce-nav-meta {
  color: var(--primary-color, #ff6a00);
}

.rce-nav-footer {
  padding: 8px;
  border-top: 1px solid var(--border-color, #e0e0e0);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rce-nav-btn {
  padding: 6px 10px;
  font-size: 12px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  background: var(--background-primary, #fff);
  color: var(--text-secondary, #666);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}
.rce-nav-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #ff6a00);
  color: var(--primary-color, #ff6a00);
}
.rce-nav-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
