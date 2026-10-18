<template>
  <section class="dashboard-card task-charts" id="task-charts">
    <div class="dashboard-card__head">
      <div class="card-head-text">
        <span class="card-title">任务统计</span>
        <p class="card-sub">任务类型、完成趋势与状态分布的全域视图</p>
      </div>
    </div>

    <div v-if="error" class="charts-error">
      <span class="charts-error-value">--</span>
      <span class="charts-error-text">{{ error }}</span>
    </div>
    <template v-else>
      <!-- ① 任务完成趋势 -->
      <div class="chart-card">
        <div class="chart-card__head">
          <span class="chart-card-title">任务完成趋势</span>
          <div class="chart-controls">
            <div class="btn-group chart-mode-group">
              <button
                type="button"
                class="chart-mode-btn"
                :class="{ active: trendMode === 'line' }"
                @click="trendMode = 'line'"
              >折线</button>
              <button
                type="button"
                class="chart-mode-btn"
                :class="{ active: trendMode === 'bar' }"
                @click="trendMode = 'bar'"
              >柱状</button>
            </div>
            <div class="btn-group chart-granularity-group">
              <button
                v-for="g in GRANULARITIES"
                :key="g.value"
                type="button"
                class="chart-mode-btn"
                :class="{ active: granularity === g.value }"
                @click="handleGranularityChange(g.value)"
              >{{ g.label }}</button>
            </div>
          </div>
        </div>
        <div class="chart-canvas-wrap">
          <canvas ref="trendChartRef"></canvas>
        </div>
      </div>

      <!-- ② 任务类型分布 -->
      <div class="chart-card">
        <div class="chart-card__head">
          <span class="chart-card-title">任务类型分布</span>
        </div>
        <div class="chart-canvas-wrap">
          <canvas ref="typeChartRef"></canvas>
        </div>
      </div>

      <!-- ③ 任务状态分布 -->
      <div class="chart-card">
        <div class="chart-card__head">
          <span class="chart-card-title">任务状态分布</span>
        </div>
        <div class="chart-canvas-wrap">
          <canvas ref="statusChartRef"></canvas>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import { Chart } from 'chart.js/auto'
import { useTaskDomainStats } from '../../../composables/dashboard/useTaskDomainStats'
import { createTaskTrendChart, createTaskTypeChart, createTaskStatusChart } from '../../../utils/chartUtils'

const GRANULARITIES = [
  { value: 'day', label: '日' },
  { value: 'week', label: '周' },
  { value: 'month', label: '月' },
  { value: 'year', label: '年' },
]

const { stats, granularity, error, load, changeGranularity } = useTaskDomainStats()
const trendChartRef = ref<HTMLCanvasElement | null>(null)
const typeChartRef = ref<HTMLCanvasElement | null>(null)
const statusChartRef = ref<HTMLCanvasElement | null>(null)

const trendMode = ref<'line' | 'bar'>('line')

let chartInstances: any[] = []

function destroyCharts() {
  chartInstances.forEach(c => c?.destroy?.())
  chartInstances = []
}

function renderCharts() {
  destroyCharts()
  if (!stats.value) return
  if (trendChartRef.value) {
    const chart = createTaskTrendChart(trendChartRef.value, stats.value.trend ?? [], { granularity: granularity.value })
    if (trendMode.value === 'bar') {
      // 柱状形态：Chart.js 同款折线图改为 bar 类型重建
      chart.destroy()
      const bar = createTaskTrendBar(trendChartRef.value, stats.value.trend ?? [], granularity.value)
      chartInstances.push(bar)
    } else {
      chartInstances.push(chart)
    }
  }
  if (typeChartRef.value) {
    chartInstances.push(createTaskTypeChart(typeChartRef.value, stats.value.typeCounts ?? { api: 0, e2e: 0, mixed: 0 }))
  }
  if (statusChartRef.value) {
    chartInstances.push(createTaskStatusChart(statusChartRef.value, stats.value.statusCounts ?? {}))
  }
}

/** 任务完成趋势柱状形态（chartUtils 折线同数据口径，bar 类型重建） */
function createTaskTrendBar(ctx: HTMLCanvasElement, trendBuckets: { key: string; count: number }[], g: string) {
  const labels = trendBuckets.map(b => b.key)
  const data = trendBuckets.map(b => b.count)
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '完成任务数',
        data,
        backgroundColor: 'rgba(255, 106, 0, 0.55)',
        borderColor: '#FF6A00',
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.1)' } },
        x: { grid: { display: true, color: 'rgba(0,0,0,0.1)' } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: 'rgba(0,0,0,0.8)', padding: 12, cornerRadius: 8, usePointStyle: true },
      },
      animation: { duration: 0, easing: 'linear' },
    },
  })
}

async function handleGranularityChange(g: string) {
  await changeGranularity(g)
  renderCharts()
}

onMounted(() => {
  load().then(renderCharts)
})

watch([trendChartRef, typeChartRef, statusChartRef], () => {
  if (trendChartRef.value && typeChartRef.value && statusChartRef.value) {
    renderCharts()
  }
}, { deep: true })

watch(trendMode, () => renderCharts())

onBeforeUnmount(() => destroyCharts())
</script>
