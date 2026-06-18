<template>
  <div class="rce-round-head">
    <div class="rce-round-head-left">
      <div class="rce-round-num">{{ round.roundNumber }}</div>
      <div>
        <div class="rce-round-label">第 {{ round.roundNumber }} 轮</div>
        <div class="rce-round-meta">
          <span v-if="round.audios?.length">
            <i class="fas fa-music"></i> {{ round.audios.length }} 条音频
          </span>
          <span v-if="round.backgroundNoise?.audioId">
            <i class="fas fa-volume-up"></i> {{ round.backgroundNoise.audioId }}
          </span>
          <span v-if="round.evaluation?.dimensions?.length">
            <i class="fas fa-chart-bar"></i> {{ round.evaluation.dimensions.length }} 维度
          </span>
        </div>
      </div>
    </div>
    <div class="rce-round-head-actions">
      <div class="rce-pager">
        <button type="button" class="rce-pager-btn" :disabled="activeIndex === 0" @click="$emit('update:activeIndex', activeIndex - 1)">
          <i class="fas fa-chevron-left"></i>
        </button>
        <span class="rce-pager-info">{{ activeIndex + 1 }} / {{ totalRounds }}</span>
        <button type="button" class="rce-pager-btn" :disabled="activeIndex === totalRounds - 1" @click="$emit('update:activeIndex', activeIndex + 1)">
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
      <button type="button" class="rce-icon-btn" title="复制轮次" @click="$emit('copy')">
        <i class="fas fa-copy"></i>
      </button>
      <button
        type="button"
        class="rce-icon-btn rce-icon-btn-danger"
        title="删除轮次"
        :disabled="totalRounds <= 1"
        @click="$emit('delete')"
      >
        <i class="fas fa-trash-alt"></i>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RoundConfigItem } from '../types'

defineProps<{
  round: RoundConfigItem
  activeIndex: number
  totalRounds: number
}>()

defineEmits<{
  'update:activeIndex': [value: number]
  'copy': []
  'delete': []
}>()
</script>

<style scoped>
.rce-round-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: var(--background-secondary, #f5f6f8);
  border-radius: 8px;
  margin-bottom: 16px;
}

.rce-round-head-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.rce-round-num {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--primary-color, #ff6a00);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rce-round-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.rce-round-meta {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: var(--text-light, #999);
  margin-top: 2px;
}
.rce-round-meta i {
  margin-right: 2px;
}

.rce-round-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rce-pager {
  display: flex;
  align-items: center;
  gap: 6px;
}

.rce-pager-btn {
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  background: var(--background-primary, #fff);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-secondary, #666);
}
.rce-pager-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.rce-pager-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #ff6a00);
  color: var(--primary-color, #ff6a00);
}

.rce-pager-info {
  font-size: 12px;
  color: var(--text-secondary, #666);
}

.rce-icon-btn {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-secondary, #666);
  transition: all 0.15s;
}
.rce-icon-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #ff6a00);
  color: var(--primary-color, #ff6a00);
}
.rce-icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.rce-icon-btn-danger:hover:not(:disabled) {
  border-color: var(--danger-color, #f44336);
  color: var(--danger-color, #f44336);
}
</style>
