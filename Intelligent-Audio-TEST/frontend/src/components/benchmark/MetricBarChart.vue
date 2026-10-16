<template>
  <div class="metric-bar-chart">
    <div class="chart-canvas-wrap" :class="{ 'chart-empty': !hasRows }">
      <canvas ref="canvasRef"></canvas>
      <div v-if="!hasRows" class="chart-placeholder">暂无图表数据</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { Chart } from 'chart.js/auto'
import type { BenchmarkRankingGroup } from '../../domain/model/benchmark'
import { BenchmarkSource, BenchmarkSourceLabels } from '../../domain/enums'
import { formatMetricValue } from '../../composables/benchmark/groupRankings'

const props = defineProps<{ group: BenchmarkRankingGroup }>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let chartInstance: Chart | null = null

const hasRows = computed(() => props.group.rows.length > 0)

/** 绘制序行：名次升序自上而下（chart.js 横向 y 轴自下而上，故翻转 labels/data 顺序） */
const sortedRows = computed(() => [...props.group.rows].sort((a, b) => b.rank - a.rank))

function buildChartData() {
  const rows = sortedRows.value
  const labels = rows.map((r) => r.subjectName)
  const values = rows.map((r) => r.metricValue)
  const sources = rows.map((r) => r.source)
  const cssVars = getComputedStyle(document.documentElement)
  const chart1 = cssVars.getPropertyValue('--chart-1').trim() || '#ff6a00'
  const chart2 = cssVars.getPropertyValue('--chart-2').trim() || '#1976d2'
  return {
    labels,
    datasets: [
      {
        label: props.group.metricName,
        data: values,
        backgroundColor: sources.map((s) =>
          s === BenchmarkSource.PLATFORM_TEST ? chart1 : chart2),
        borderRadius: 3,
        barPercentage: 0.6,
      },
    ],
  }
}

function renderChart() {
  if (!canvasRef.value) return
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
  if (!hasRows.value) return

  const ctx = canvasRef.value.getContext('2d')
  if (!ctx) return

  const cssVars = getComputedStyle(document.documentElement)
  const gridColor = cssVars.getPropertyValue('--border').trim() || 'rgba(0,0,0,0.08)'

  chartInstance = new Chart(ctx, {
    type: 'bar',
    data: buildChartData(),
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
              // indexAxis:'y' 横向条形：parsed.x = 数据值、parsed.y = 类别下标（chart.js v4）
              const row = sortedRows.value[item.dataIndex]
              const source = row
                ? BenchmarkSourceLabels[row.source] || row.source
                : ''
              const unit = props.group.unit ? props.group.unit : ''
              return ` ${formatMetricValue(item.parsed.x)}${unit} · ${source}`
            },
          },
        },
      },
      scales: {
        x: {
          // borderDash 为 chart.js v4 网格线运行时属性（类型声明缺失，此处显式标注）
          grid: { color: gridColor, borderDash: [3, 3] } as { color: string; borderDash: number[] },
          title: {
            display: !!props.group.unit,
            text: props.group.unit || '',
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

onMounted(renderChart)

watch(() => props.group, () => {
  renderChart()
}, { deep: true })

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
})
</script>

<style scoped>
.chart-canvas-wrap {
  position: relative;
  height: 240px;
  width: 100%;
}
@media (min-width: 640px) {
  .chart-canvas-wrap {
    height: 288px;
  }
}
.chart-placeholder {
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
