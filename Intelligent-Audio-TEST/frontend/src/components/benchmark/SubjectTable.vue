<template>
  <div class="subject-table" role="region" aria-label="排行明细表：名次、主体、主体类型、来源、版本、指标值、归一化分、百分位、差距、基线差、计算于">
    <table class="rank-table">
      <thead>
        <tr>
          <th class="col-rank">名次</th>
          <th class="col-subject">主体</th>
          <th>主体类型</th>
          <th>来源</th>
          <th>版本</th>
          <th class="col-numeric">指标值（{{ group.unit || '—' }}）</th>
          <th class="col-numeric">归一化分</th>
          <th class="col-numeric">百分位</th>
          <th class="col-numeric">与最佳差</th>
          <th class="col-numeric">与中位差</th>
          <th class="col-numeric">基线差</th>
          <th>计算于</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in group.rows" :key="row.id" :class="{ 'row-highlighted': isHighlighted(row.subjectName) }">
          <td class="col-rank mono">{{ row.rank }}</td>
          <td class="col-subject">
            <button class="subject-link" type="button" @click="$emit('selectSubject', row.subjectName)">
              {{ row.subjectName }}
            </button>
          </td>
          <td>{{ subjectTypeLabel(row) }}</td>
          <td><span class="source-cell">{{ sourceLabel(row) }}</span></td>
          <td class="mono">{{ versionLabel(row) }}</td>
          <td class="col-numeric mono">{{ formatMetricValue(row.metricValue) }}</td>
          <td class="col-numeric mono">{{ row.score100 ?? '—' }}</td>
          <td class="col-numeric mono">{{ row.percentile ?? '—' }}</td>
          <td class="col-numeric mono">{{ row.gapBest ?? '—' }}</td>
          <td class="col-numeric mono">{{ row.gapMedian ?? '—' }}</td>
          <td class="col-numeric mono">
            <template v-if="row.deltaExternal != null">{{ row.deltaExternal > 0 ? '+' : '' }}{{ row.deltaExternal }}</template>
            <template v-else>—</template>
          </td>
          <td class="mono">{{ formatComputedAt(row.computedAt) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { BenchmarkRankingGroup, BenchmarkRankingRow } from '../../domain/model/benchmark'
import {
  BenchmarkSource,
  BenchmarkSourceLabels,
  BenchmarkSubjectTypeLabels,
  BenchmarkDeviceTypeLabels,
  type BenchmarkSubjectTypeType,
} from '../../domain/enums'
import { formatMetricValue, formatComputedAt } from '../../composables/benchmark/groupRankings'

const props = defineProps<{
  group: BenchmarkRankingGroup
  highlightedSubject?: string
}>()

defineEmits<{
  (e: 'selectSubject', subjectName: string): void
}>()

function isHighlighted(subject: string): boolean {
  return !!props.highlightedSubject && subject === props.highlightedSubject
}

function subjectTypeLabel(row: BenchmarkRankingRow): string {
  return BenchmarkSubjectTypeLabels[row.subjectType as BenchmarkSubjectTypeType] || row.subjectType
}

function sourceLabel(row: BenchmarkRankingRow): string {
  return BenchmarkSourceLabels[row.source] || row.source
}

function versionLabel(row: BenchmarkRankingRow): string {
  return row.source === BenchmarkSource.PLATFORM_TEST && row.publishedTaskVersion != null
    ? `v${row.publishedTaskVersion}`
    : '—'
}
</script>

<style scoped>
.subject-table {
  overflow-x: auto;
  max-width: 100%;
}
.rank-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.rank-table th,
.rank-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.rank-table th {
  font-weight: 600;
  color: var(--muted-foreground);
  background: var(--muted);
  position: sticky;
  top: 0;
}
.rank-table td.col-numeric {
  text-align: right;
}
.rank-table th.col-numeric {
  text-align: right;
}
.mono {
  font-family: var(--font-family-mono, monospace);
  font-variant-numeric: tabular-nums;
}
.col-rank {
  width: 48px;
}
.col-subject {
  min-width: 180px;
}
.subject-link {
  background: none;
  border: none;
  padding: 0;
  font-family: var(--font-family-mono, monospace);
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: var(--border);
  text-underline-offset: 3px;
  text-decoration-thickness: 1px;
}
.subject-link:hover {
  color: var(--primary);
  text-decoration-color: var(--primary);
}
.source-cell {
  color: var(--muted-foreground);
}
</style>
