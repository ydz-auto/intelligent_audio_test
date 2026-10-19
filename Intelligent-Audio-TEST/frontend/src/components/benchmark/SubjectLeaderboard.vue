<template>
  <div class="subject-leaderboard">
    <div v-if="!rows.length" class="leaderboard-empty">
      暂无榜单数据
    </div>
    <div v-else class="leaderboard-grid">
      <div class="leaderboard-column" v-for="(column, colIdx) in columns" :key="colIdx">
        <div
          v-for="row in column"
          :key="row.id"
          class="leaderboard-row"
          :class="{ 'row-highlighted': isHighlighted(row.subjectName) }"
        >
          <div class="rank-cell">{{ row.rank }}.</div>
          <div class="subject-cell">
            <button
              class="subject-link"
              type="button"
              :title="`按主体「${row.subjectName}」筛选`"
              @click="$emit('selectSubject', row.subjectName)"
            >
              {{ row.subjectName }}
            </button>
            <BenchmarkBadges :row="row" />
          </div>
          <div class="value-cell">
            <div class="metric-value">
              {{ formatMetricValue(row.metricValue) }}<span v-if="row.unit" class="metric-unit">{{ row.unit }}</span>
            </div>
            <div class="metric-sub">
              <DeltaText :row="row" />
              <router-link
                v-if="showReport && row.source === BenchmarkSource.PLATFORM_TEST && row.reportId != null"
                class="report-link"
                :to="{ name: 'reportView', params: { id: String(row.reportId) } }"
              >
                <i class="fas fa-file-text"></i> 查看报告
              </router-link>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/components/button.css'

import { computed } from 'vue'
import type { BenchmarkRankingRow } from '../../domain/model/benchmark'
import { BenchmarkSource } from '../../domain/enums'
import BenchmarkBadges from './BenchmarkBadges.vue'
import DeltaText from './DeltaText.vue'
import { formatMetricValue } from '../../composables/benchmark/groupRankings'

const props = defineProps<{
  /** 组内榜单行（已按名次升序） */
  rows: BenchmarkRankingRow[]
  /** 当前主体筛选值（命中行高亮） */
  highlightedSubject?: string
  /** 是否渲染「查看报告」链接（report:read 门控） */
  showReport?: boolean
}>()

defineEmits<{
  (e: 'selectSubject', subjectName: string): void
}>()

/** 双栏均分（半列 = ceil(n/2)，对位 INT-359 §4.4 双栏榜单） */
const columns = computed<BenchmarkRankingRow[][]>(() => {
  const rows = props.rows
  const half = Math.ceil(rows.length / 2)
  return [rows.slice(0, half), rows.slice(half)]
})

function isHighlighted(subject: string): boolean {
  return !!props.highlightedSubject && subject === props.highlightedSubject
}
</script>

<style scoped>
.leaderboard-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0 32px;
}
@media (min-width: 768px) {
  .leaderboard-grid {
    grid-template-columns: 1fr 1fr;
  }
}
.leaderboard-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.leaderboard-column:last-child .leaderboard-row:last-child {
  border-bottom: none;
}
.rank-cell {
  width: 24px;
  flex-shrink: 0;
  text-align: right;
  font-family: var(--font-family-mono, monospace);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--muted-foreground);
  padding-top: 2px;
}
.subject-cell {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.subject-link {
  align-self: flex-start;
  background: none;
  border: none;
  padding: 0;
  font-family: var(--font-family-mono, monospace);
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: var(--border);
  text-underline-offset: 4px;
  text-decoration-thickness: 1px;
  text-align: left;
}
.subject-link:hover {
  text-decoration-color: var(--primary);
  color: var(--primary);
}
.value-cell {
  flex-shrink: 0;
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.metric-value {
  font-family: var(--font-family-mono, monospace);
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--foreground);
}
.metric-unit {
  margin-left: 2px;
  font-size: 11px;
  font-weight: 400;
  color: var(--muted-foreground);
}
.metric-sub {
  display: flex;
  align-items: center;
  gap: 8px;
}
.report-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--secondary);
  text-decoration: none;
}
.report-link:hover {
  text-decoration: underline;
}
.row-highlighted .subject-link {
  color: var(--primary);
  text-decoration-color: var(--primary);
}
.leaderboard-empty {
  padding: 16px 20px;
  text-align: center;
  font-size: 13px;
  color: var(--muted-foreground);
}
</style>
