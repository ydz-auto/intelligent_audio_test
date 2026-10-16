<template>
  <div class="ranking-filters">
    <div class="filter-row">
      <label class="filter-item">
        <span class="filter-label">测试集</span>
        <select
          class="filter-select"
          :value="suite"
          @change="$emit('update:suite', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">全部测试集</option>
          <option v-for="s in suiteOptions" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>

      <label class="filter-item">
        <span class="filter-label">指标</span>
        <select
          class="filter-select"
          :value="metricCode"
          @change="$emit('update:metricCode', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">全部指标</option>
          <option v-for="m in metricOptions" :key="m.id" :value="m.metricCode">{{ m.metricName }}</option>
        </select>
      </label>

      <label class="filter-item">
        <span class="filter-label">数据来源</span>
        <select
          class="filter-select"
          :value="source"
          @change="$emit('update:source', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="opt in sourceOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </label>

      <div class="filter-item filter-search">
        <span class="filter-label">搜索主体</span>
        <div class="search-box">
          <i class="fas fa-search search-icon" aria-hidden="true"></i>
          <input
            class="search-input"
            type="text"
            :value="subjectName"
            placeholder="搜索主体名称…"
            @input="handleSubjectInput"
          />
        </div>
      </div>

      <button
        v-if="hasActiveFilters"
        type="button"
        class="btn btn-reset"
        @click="$emit('reset')"
      >
        <i class="fas fa-undo"></i> 重置
      </button>

      <button
        v-if="hasComputePermission"
        type="button"
        class="btn btn-compute"
        :disabled="computing"
        @click="openConfirm"
      >
        <i v-if="computing" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-calculator"></i>
        {{ computing ? '计算中…' : '立即计算' }}
      </button>

      <span class="pending-note">按算法过滤待后端立项</span>
    </div>

    <!-- 重算确认弹窗 -->
    <div v-if="showConfirm" class="confirm-mask">
      <div class="confirm-dialog" role="alertdialog" aria-modal="true" aria-label="重新计算排行">
        <h4 class="confirm-title">重新计算排行？</h4>
        <p class="confirm-desc">将合并平台实测与外部基线全量重算，期间现有排行保持可查看。</p>
        <div class="confirm-actions">
          <button type="button" class="btn btn-cancel" @click="showConfirm = false">取消</button>
          <button type="button" class="btn btn-confirm" :disabled="computing" @click="handleConfirm">
            {{ computing ? '计算中…' : '开始计算' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { BENCHMARK_SOURCE_OPTIONS } from '../../store/benchmarkStore'
import type { MetricMappingInfo } from '../../domain/model/benchmark'
import type { BenchmarkSourceType } from '../../domain/enums'

const props = defineProps<{
  suite: string
  metricCode: string
  source: string
  subjectName: string
  suiteOptions: string[]
  metricOptions: MetricMappingInfo[]
  hasActiveFilters: boolean
  hasComputePermission: boolean
  computing: boolean
}>()

const emit = defineEmits<{
  (e: 'update:suite', value: string): void
  (e: 'update:metricCode', value: string): void
  (e: 'update:source', value: string): void
  (e: 'update:subjectName', value: string): void
  (e: 'subjectSearch', value: string): void
  (e: 'reset'): void
  (e: 'compute'): void
}>()

const sourceOptions = BENCHMARK_SOURCE_OPTIONS

const showConfirm = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function handleSubjectInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('update:subjectName', value)
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('subjectSearch', value)
  }, 300)
}

function openConfirm() {
  showConfirm.value = true
}

function handleConfirm() {
  showConfirm.value = false
  emit('compute')
}
</script>

<style scoped>
.ranking-filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.filter-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.filter-label {
  font-size: 13px;
  color: var(--muted-foreground);
}
.filter-select {
  height: 32px;
  min-width: 110px;
  padding: 0 8px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--foreground);
  font-size: 13px;
  outline: none;
}
.filter-select:focus {
  border-color: var(--primary);
}
.search-box {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.search-icon {
  position: absolute;
  left: 8px;
  font-size: 12px;
  color: var(--muted-foreground);
}
.search-input {
  height: 32px;
  width: 180px;
  padding: 0 8px 0 26px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--foreground);
  font-size: 13px;
  outline: none;
}
.search-input:focus {
  border-color: var(--primary);
}
.btn {
  height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
}
.btn-reset {
  background: transparent;
  border-color: var(--border);
  color: var(--muted-foreground);
}
.btn-reset:hover {
  color: var(--foreground);
  border-color: var(--foreground);
}
.btn-compute {
  background: var(--primary);
  color: var(--primary-foreground);
}
.btn-compute:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.pending-note {
  font-size: 12px;
  color: var(--muted-foreground);
}
.confirm-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
}
.confirm-dialog {
  width: 400px;
  max-width: calc(100vw - 32px);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
}
.confirm-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}
.confirm-desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--muted-foreground);
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.btn-cancel {
  background: transparent;
  border-color: var(--border);
  color: var(--muted-foreground);
}
.btn-confirm {
  background: var(--primary);
  color: var(--primary-foreground);
}
.btn-confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
