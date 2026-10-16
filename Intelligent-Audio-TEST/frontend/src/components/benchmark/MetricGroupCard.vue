<template>
  <section class="metric-group-card">
    <!-- 卡头 -->
    <div class="card-header">
      <div class="header-left">
        <div class="header-title-row">
          <i class="header-icon" :class="categoryIcon" aria-hidden="true"></i>
          <h3 class="group-title">{{ group.metricName }} · {{ group.scenarioKey }}</h3>
          <span class="direction-badge" :class="directionBadgeClass">{{ directionLabel }}</span>
        </div>
        <p class="group-description">
          平台实测与外部基线按{{ directionLabel }}排名，共 {{ group.total }} 个主体参与。
        </p>
      </div>
      <div class="header-right">
        <div class="subject-count">{{ group.total }}</div>
        <div class="subject-count-label">个主体 · 计算于 {{ formatComputedAt(group.computedAt) }}</div>
      </div>
    </div>

    <!-- 指标值对比条形图（前端派生，无新后端依赖） -->
    <div class="chart-area">
      <MetricBarChart :group="group" />
    </div>

    <!-- 榜单块（列表 / 表格双视图） -->
    <div class="leaderboard-block">
      <div class="leaderboard-header">
        <div class="leaderboard-title-row">
          <i class="fas fa-trophy trophy-icon" aria-hidden="true"></i>
          <span class="leaderboard-title">榜单</span>
          <span class="leaderboard-desc">按名次排列，实测轨取最新版本参与对比。</span>
        </div>
        <div class="view-switch" role="tablist" aria-label="榜单视图">
          <button
            type="button"
            class="view-switch-btn"
            :class="{ active: viewMode === 'list' }"
            role="tab"
            :aria-selected="viewMode === 'list'"
            @click="switchView('list')"
          >列表</button>
          <button
            type="button"
            class="view-switch-btn"
            :class="{ active: viewMode === 'table' }"
            role="tab"
            :aria-selected="viewMode === 'table'"
            @click="switchView('table')"
          >表格</button>
        </div>
      </div>
      <SubjectLeaderboard
        v-if="viewMode === 'list'"
        :rows="group.rows"
        :highlighted-subject="highlightedSubject"
        :show-report="showReport"
        @select-subject="$emit('selectSubject', $event)"
      />
      <SubjectTable
        v-else
        :group="group"
        :highlighted-subject="highlightedSubject"
        @select-subject="$emit('selectSubject', $event)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { BenchmarkRankingGroup } from '../../domain/model/benchmark'
import {
  BenchmarkCategory,
  BenchmarkDirection,
  BenchmarkDirectionLabels,
  type BenchmarkCategoryType,
} from '../../domain/enums'
import MetricBarChart from './MetricBarChart.vue'
import SubjectLeaderboard from './SubjectLeaderboard.vue'
import SubjectTable from './SubjectTable.vue'
import { formatComputedAt } from '../../composables/benchmark/groupRankings'

const props = defineProps<{
  group: BenchmarkRankingGroup
  highlightedSubject?: string
  showReport?: boolean
}>()

defineEmits<{ (e: 'selectSubject', subjectName: string): void }>()

/** 视图选择存 localStorage（INT-359 §5.3：不入 URL） */
const VIEW_KEY = 'iatp:rankings:v1:view'
const viewMode = ref<string>(
  localStorage.getItem(VIEW_KEY) === 'table' ? 'table' : 'list',
)

function switchView(mode: 'list' | 'table') {
  viewMode.value = mode
  try {
    localStorage.setItem(VIEW_KEY, mode)
  } catch {
    // localStorage 不可用（隐私模式）时仅内存态
  }
}

const categoryIcon = computed<string>(() => {
  switch (props.group.category as BenchmarkCategoryType) {
    case BenchmarkCategory.ASR:
      return 'fas fa-microphone'
    case BenchmarkCategory.VOICE_LLM:
      return 'fas fa-comments'
    case BenchmarkCategory.TTS:
      return 'fas fa-volume-high'
    case BenchmarkCategory.TRANSLATION:
      return 'fas fa-language'
    default:
      return 'fas fa-chart-simple'
  }
})

const directionLabel = computed(() =>
  BenchmarkDirectionLabels[props.group.direction] || props.group.direction)

const directionBadgeClass = computed(() =>
  props.group.direction === BenchmarkDirection.HIGHER_IS_BETTER ? 'badge-higher' : 'badge-lower')
</script>

<style scoped>
.metric-group-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
}
.header-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.header-icon {
  font-size: 15px;
  color: var(--primary);
}
.group-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  margin: 0;
}
.direction-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.6;
}
.badge-higher {
  background: var(--primary);
  color: var(--primary-foreground);
}
.badge-lower {
  background: var(--muted);
  color: var(--muted-foreground);
}
.group-description {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted-foreground);
}
.header-right {
  flex-shrink: 0;
  text-align: right;
}
.subject-count {
  font-family: var(--font-family-mono, monospace);
  font-size: 24px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  color: var(--foreground);
}
.subject-count-label {
  margin-top: 4px;
  font-size: 10px;
  letter-spacing: 0.05em;
  color: var(--muted-foreground);
}
.chart-area {
  padding: 0 20px 20px;
}
.leaderboard-block {
  border-top: 1px solid var(--border);
}
.leaderboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px 8px;
}
.leaderboard-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.trophy-icon {
  font-size: 13px;
  color: var(--warning);
}
.leaderboard-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}
.leaderboard-desc {
  font-size: 12px;
  color: var(--muted-foreground);
}
.view-switch {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}
.view-switch-btn {
  background: transparent;
  border: none;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--muted-foreground);
  cursor: pointer;
}
.view-switch-btn.active {
  background: var(--primary);
  color: var(--primary-foreground);
}
.view-switch-btn:not(.active):hover {
  background: var(--muted);
  color: var(--foreground);
}
</style>
