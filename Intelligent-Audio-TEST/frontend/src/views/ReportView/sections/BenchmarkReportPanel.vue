<template>
  <section class="bmr-panel">
    <!-- 加载态 -->
    <div v-if="loading" class="bmr-state">
      <div class="bmr-spinner"></div>
      <p>正在加载 Benchmark 排行快照...</p>
    </div>

    <!-- 错误态 -->
    <div v-else-if="error" class="bmr-state bmr-error">
      <i class="fas fa-exclamation-triangle"></i>
      <p>{{ error }}</p>
    </div>

    <!-- 无快照数据兜底（记录找不到 / ranking_data 缺失） -->
    <div v-else-if="!record || !snapshot" class="bmr-state">
      <i class="fas fa-trophy"></i>
      <p>该 Benchmark 报告暂无可展示的排行快照数据</p>
      <p v-if="fallbackDesc" class="bmr-fallback-desc">{{ fallbackDesc }}</p>
    </div>

    <!-- 正常渲染 -->
    <template v-else>
      <div class="bmr-header">
        <div class="bmr-title-row">
          <h3 class="bmr-title">{{ report.name || 'Benchmark 报告' }}</h3>
          <span class="bmr-badge">Benchmark 报告</span>
        </div>
        <div class="bmr-meta-chips">
          <span class="bmr-chip" v-if="record.suite" title="测试集标识"><i class="fas fa-database"></i> {{ record.suite }}</span>
          <span class="bmr-chip" v-if="record.category" title="被测类别"><i class="fas fa-tag"></i> {{ categoryLabel }}</span>
          <span class="bmr-chip" v-if="record.source" title="数据来源"><i class="fas fa-source"></i> {{ sourceLabel }}</span>
          <span class="bmr-chip" v-if="record.version" title="版本"><i class="fas fa-code-branch"></i> v{{ record.version }}</span>
          <span class="bmr-chip" v-if="record.publishedAt" title="发布时间"><i class="fas fa-clock"></i> {{ formatDate(record.publishedAt) }}</span>
          <span class="bmr-chip" v-if="record.publishedBy" title="发布人"><i class="fas fa-user"></i> {{ record.publishedBy }}</span>
        </div>
      </div>

      <!-- 快照统计卡 -->
      <div class="bmr-counts">
        <div class="bmr-count-card">
          <span class="bmr-count-value">{{ record.publishedTaskCount }}</span>
          <span class="bmr-count-label">参与任务</span>
        </div>
        <div class="bmr-count-card">
          <span class="bmr-count-value">{{ record.subjectCount }}</span>
          <span class="bmr-count-label">被测主体</span>
        </div>
        <div class="bmr-count-card">
          <span class="bmr-count-value">{{ record.metricCount }}</span>
          <span class="bmr-count-label">指标数</span>
        </div>
        <div class="bmr-count-card">
          <span class="bmr-count-value">{{ snapshot.counts.rowCount }}</span>
          <span class="bmr-count-label">排行行数</span>
        </div>
      </div>

      <!-- 排行区块：指标组页签 + 榜单 + 对比条形图 -->
      <div class="bmr-ranking" v-if="groups.length > 0">
        <div class="bmr-section-title">
          <i class="fas fa-ranking-star"></i> 排行区块（发布时点快照）
        </div>

        <div class="bmr-group-tabs" role="tablist">
          <button
            v-for="(group, index) in groups"
            :key="groupKey(group)"
            class="bmr-group-tab"
            :class="{ active: activeGroupIndex === index }"
            role="tab"
            :aria-selected="activeGroupIndex === index"
            @click="activeGroupIndex = index"
          >
            {{ groupTitle(group) }}
          </button>
        </div>

        <div v-if="activeGroup" class="bmr-group-body">
          <div class="bmr-group-meta">
            <span v-if="activeGroup.scenarioKey" class="bmr-chip"><i class="fas fa-cubes"></i> {{ activeGroup.scenarioKey }}</span>
            <span v-if="activeGroup.direction" class="bmr-chip">{{ directionLabel(activeGroup.direction) }}</span>
            <span class="bmr-chip"><i class="fas fa-arrow-trend-up"></i> {{ activeGroup.unit }}</span>
          </div>

          <div class="bmr-leaderboard">
            <table class="bmr-table">
              <thead>
                <tr>
                  <th>名次</th>
                  <th>被测主体</th>
                  <th>指标值</th>
                  <th>数据来源</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in activeGroup.rows" :key="row.id">
                  <td class="bmr-rank">{{ row.rank }}</td>
                  <td class="bmr-subject">{{ row.subjectName }}</td>
                  <td class="bmr-value">{{ formatMetricValue(row.metricValue) }}<span v-if="activeGroup.unit" class="bmr-unit"> {{ activeGroup.unit }}</span></td>
                  <td><span class="bmr-source-chip" :class="`bmr-source-${row.source}`">{{ sourceLabelFor(row.source) }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="bmr-chart-block">
            <div class="bmr-chart-title">指标对比（{{ activeGroup.metricName }}）</div>
            <div class="bmr-chart-canvas-wrap" :class="{ 'bmr-chart-empty': activeGroup.rows.length === 0 }">
              <canvas ref="chartCanvas"></canvas>
              <div v-if="activeGroup.rows.length === 0" class="bmr-chart-placeholder">暂无图表数据</div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { Chart } from 'chart.js/auto'
import { benchmarkReportsPort } from '../../../composables/benchmark/benchmarkReportsPort'
import {
  groupSnapshotRows,
  directionLabel,
  formatMetricValue,
  type BenchmarkSnapshotGroup,
} from '../../../composables/benchmark/benchmarkReportGroups'
import type { BenchmarkReportRecord, BenchmarkSnapshotRow } from '../../../domain/model/benchmarkReport'
import {
  BenchmarkReportSource,
  BenchmarkReportSourceLabels,
  type BenchmarkReportSourceType,
} from '../../../domain/model/benchmarkReport'
import { BenchmarkCategoryLabels, type BenchmarkCategoryType } from '../../../domain/enums'

const props = defineProps<{
  /** 报告聚合根（report_type='benchmark'，config 承载 suite/category/source 发布元数据） */
  report: any
}>()

const loading = ref(true)
const error = ref('')
const record = ref<BenchmarkReportRecord | null>(null)
const activeGroupIndex = ref(0)
const chartCanvas = ref<HTMLCanvasElement | null>(null)
let chartInstance: Chart | null = null

/** 发布元数据（聚合根 config 兜底；record 落库后以 record 为准） */
const publishMeta = computed(() => {
  const config = props.report?.config || {}
  return {
    suite: config.suite ?? '',
    category: config.category ?? '',
    source: config.source ?? '',
  }
})

const snapshot = computed(() => record.value?.rankingData ?? null)
const groups = computed(() => (snapshot.value ? groupSnapshotRows(snapshot.value.rows) : []))
const activeGroup = computed<BenchmarkSnapshotGroup | null>(
  () => groups.value[activeGroupIndex.value] ?? null
)

const categoryLabel = computed(() => {
  const c = record.value?.category || publishMeta.value.category
  return BenchmarkCategoryLabels[c as BenchmarkCategoryType] || c || ''
})

const sourceLabel = computed(() => {
  const s = record.value?.source || publishMeta.value.source
  return sourceLabelFor(s)
})

const fallbackDesc = computed(() => {
  const meta = publishMeta.value
  const parts = [meta.suite, categoryLabel.value, sourceLabel.value].filter((v) => !!v)
  return parts.length ? `发布参数：${parts.join(' / ')}` : ''
})

function sourceLabelFor(source: string): string {
  return BenchmarkReportSourceLabels[source as BenchmarkReportSourceType] || source || '未指定'
}

function groupKey(group: BenchmarkSnapshotGroup): string {
  return `${group.category}\u0000${group.metricCode}\u0000${group.scenarioKey}`
}

function groupTitle(group: BenchmarkSnapshotGroup): string {
  const cat = BenchmarkCategoryLabels[group.category as BenchmarkCategoryType] || group.category || '全量'
  return `${cat} · ${group.metricName}`
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 解析 benchmark_reports 记录：以报告 id 反查发布记录 → 详情取排行快照 */
async function load() {
  loading.value = true
  error.value = ''
  try {
    const meta = publishMeta.value
    const page = await benchmarkReportsPort.list({
      suite: meta.suite || undefined,
      category: meta.category || undefined,
      source: meta.source || undefined,
      perPage: 100,
    })
    const match = (page.items || []).find((item) => Number(item.reportId) === Number(props.report?.id))
    if (match) {
      record.value = await benchmarkReportsPort.getOne(match.id)
    } else {
      record.value = null
    }
  } catch (e: any) {
    console.error('加载 Benchmark 报告排行快照失败:', e)
    error.value = e?.message || '加载 Benchmark 报告排行快照失败'
    record.value = null
  } finally {
    loading.value = false
  }
}

// ===== chart.js 横向条形图（沿用主库 chart.js，零新依赖） =====
function buildChartData(rows: BenchmarkSnapshotRow[]) {
  // 绘制序反转（chart.js 横向 y 轴自下而上，名次升序自上而下）
  const sorted = [...rows].sort((a, b) => b.rank - a.rank)
  const cssVars = getComputedStyle(document.documentElement)
  const chart1 = cssVars.getPropertyValue('--chart-1').trim() || '#ff6a00'
  const chart2 = cssVars.getPropertyValue('--chart-2').trim() || '#1976d2'
  return {
    labels: sorted.map((r) => r.subjectName),
    datasets: [
      {
        label: activeGroup.value?.metricName || '',
        data: sorted.map((r) => r.metricValue),
        backgroundColor: sorted.map((r) =>
          r.source === BenchmarkReportSource.PLATFORM_TEST ? chart1 : chart2
        ),
        borderRadius: 3,
        barPercentage: 0.6,
      },
    ],
  }
}

function renderChart() {
  if (!chartCanvas.value) return
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
  if (!activeGroup.value || activeGroup.value.rows.length === 0) return

  const ctx = chartCanvas.value.getContext('2d')
  if (!ctx) return

  const cssVars = getComputedStyle(document.documentElement)
  const gridColor = cssVars.getPropertyValue('--border').trim() || 'rgba(0,0,0,0.08)'

  chartInstance = new Chart(ctx, {
    type: 'bar',
    data: buildChartData(activeGroup.value.rows),
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      animation: { duration: 0 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => items[0]?.label || '',
            label: (item) => {
              const row = activeGroup.value?.rows.find((r) => r.subjectName === item.label)
              const source = row ? sourceLabelFor(row.source) : ''
              const unit = activeGroup.value?.unit ? ` ${activeGroup.value.unit}` : ''
              return ` ${formatMetricValue(item.parsed.y)}${unit} · ${source}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: gridColor, borderDash: [3, 3] } as { color: string; borderDash: number[] },
          title: {
            display: !!activeGroup.value?.unit,
            text: activeGroup.value?.unit || '',
            color: cssVars.getPropertyValue('--muted-foreground').trim() || undefined,
          },
          ticks: {
            callback: (value) => formatMetricValue(Number(value)),
          },
        },
        y: {
          grid: { display: false },
          ticks: {
            autoSkip: false,
            font: { size: 11 },
            callback: (value) => String(value),
          },
        },
      },
    },
  })
}

watch(activeGroup, () => {
  renderChart()
}, { deep: true })

onMounted(() => {
  load()
})

watch(loading, (val) => {
  if (!val) {
    // 数据就绪后渲染图表（canvas 已挂载）
    setTimeout(() => renderChart(), 0)
  }
})

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
})
</script>

<style scoped>
.bmr-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--border-radius-lg);
  font-size: 14px;
  color: var(--color-gray-800);
}

.bmr-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  text-align: center;
  color: var(--muted-foreground);
}

.bmr-state i {
  font-size: 40px;
  color: var(--muted-foreground);
}

.bmr-error {
  color: var(--danger-color);
}

.bmr-error i {
  color: var(--danger-color);
}

.bmr-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: bmr-spin 0.8s linear infinite;
}

@keyframes bmr-spin {
  to { transform: rotate(360deg); }
}

.bmr-fallback-desc {
  font-size: 12px;
  color: var(--muted-foreground);
}

.bmr-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bmr-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bmr-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-gray-800);
}

.bmr-badge {
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 600;
}

.bmr-meta-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.bmr-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-6);
  background: var(--muted);
  color: var(--text-secondary);
  font-size: 12px;
}

.bmr-counts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}

.bmr-count-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px 8px;
  border-radius: var(--radius-10);
  background: var(--muted);
}

.bmr-count-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--primary-color);
}

.bmr-count-label {
  font-size: 12px;
  color: var(--muted-foreground);
}

.bmr-ranking {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.bmr-section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-gray-800);
}

.bmr-group-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.bmr-group-tab {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: transparent;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.bmr-group-tab:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.bmr-group-tab.active {
  background: var(--primary-color);
  border-color: var(--primary-color);
  color: var(--color-white);
}

.bmr-group-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.bmr-group-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.bmr-leaderboard {
  border: 1px solid var(--border);
  border-radius: var(--radius-10);
  overflow: hidden;
}

.bmr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.bmr-table th,
.bmr-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.bmr-table th {
  background: var(--muted);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
}

.bmr-table tr:last-child td {
  border-bottom: none;
}

.bmr-rank {
  font-weight: 700;
  color: var(--primary-color);
}

.bmr-subject {
  font-weight: 500;
}

.bmr-value {
  font-variant-numeric: tabular-nums;
}

.bmr-unit {
  color: var(--muted-foreground);
  font-size: 12px;
}

.bmr-source-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 12px;
}

.bmr-source-platform_test {
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--chart-1);
}

.bmr-source-external_import {
  background: color-mix(in srgb, var(--secondary) 12%, transparent);
  color: var(--chart-2);
}

.bmr-chart-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bmr-chart-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.bmr-chart-canvas-wrap {
  position: relative;
  height: 260px;
  width: 100%;
}

.bmr-chart-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--muted-foreground);
  background: var(--muted);
}
</style>
