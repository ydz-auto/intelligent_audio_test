<template>
  <div class="rst-statistics-view">
    <!-- Toast 提示 -->
    <teleport to="#global-fixed-elements">
      <div v-if="toast" class="rst-toast-container" :class="`rst-toast-${toast.type}`">
        <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : toast.type === 'warning' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle'"></i>
        <span>{{ toast.message }}</span>
      </div>
    </teleport>

    <!-- 页面标题 -->
    <div class="page-header rst-page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-chart-line"></i>
          报告统计分析
        </h2>
        <p class="page-description">报告数量 / 用例执行 / 评估指标 / 设备性能 多维度统计分析</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goBack">
          <i class="fas fa-arrow-left"></i> 返回报告中心
        </button>
      </div>
    </div>

    <!-- 统计控制区：维度 + 时间范围 + 执行入口 -->
    <section class="card rst-control-section">
      <div class="rst-control-row">
        <div class="rst-control-item">
          <label>统计维度：</label>
          <select class="rst-select" v-model="dimension">
            <option v-for="opt in DIMENSION_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <div class="rst-control-item">
          <label>统计时间范围：</label>
          <input type="date" class="date-input" v-model="startDate" />
          <span>至</span>
          <input type="date" class="date-input" v-model="endDate" />
        </div>
        <div class="rst-control-item">
          <button class="btn btn-primary" @click="handleExecute" :disabled="statisticsLoading">
            <i class="fas fa-play" :class="{ 'fa-spin': statisticsLoading }"></i> 执行统计分析
          </button>
        </div>
      </div>
    </section>

    <!-- 四页签：统计维度 / 统计结果 / 趋势分析 / 报表生成 -->
    <div class="rst-tabs" role="tablist">
      <button
        v-for="tab in STATISTICS_TABS"
        :key="tab.value"
        class="rst-tab"
        :class="{ active: activeTab === tab.value }"
        role="tab"
        :aria-selected="activeTab === tab.value"
        @click="handleTabChange(tab.value)"
      >
        <i :class="tab.icon"></i>
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <!-- 页签 1：统计维度 -->
    <section v-if="activeTab === 'dimension'" class="rst-pane">
      <div class="rst-sub-description">
        <p>按维度与时间范围配置统计分析口径。当前维度：{{ getDimensionLabel(dimension) }}。</p>
      </div>
      <div class="rst-dimension-grid">
        <div v-for="opt in DIMENSION_OPTIONS" :key="opt.value" class="card rst-dimension-card" :class="{ 'rst-dimension-card--active': dimension === opt.value }" @click="dimension = opt.value">
          <i :class="getDimensionIcon(opt.value)"></i>
          <span class="rst-dimension-name">{{ opt.label }}</span>
          <span class="rst-dimension-desc">{{ getDimensionDesc(opt.value) }}</span>
        </div>
      </div>

      <!-- 统计加载 / 错误 / 结果 -->
      <div v-if="statisticsLoading" class="rst-loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <p>正在统计分析...</p>
      </div>
      <div v-else-if="statisticsError" class="rst-error-state">
        <i class="fas fa-exclamation-circle"></i>
        <p>{{ statisticsError }}</p>
        <button class="btn btn-secondary btn-sm" @click="handleExecute">
          <i class="fas fa-redo"></i> 重试
        </button>
      </div>
      <div v-else-if="statisticsData" class="rst-section">
        <h4 class="rst-section-title">当前维度统计概览（{{ getDimensionLabel(statisticsData.dimension) }}）</h4>
        <div class="rst-overview-grid">
          <div v-for="item in overviewItems" :key="item.label" class="card rst-overview-card">
            <span class="rst-overview-label">{{ item.label }}</span>
            <span class="rst-overview-value">{{ item.value }}</span>
          </div>
        </div>
      </div>
      <div v-else class="rst-empty-state">
        <i class="fas fa-chart-column"></i>
        <p>暂无统计数据，请点击上方「执行统计分析」</p>
      </div>
    </section>

    <!-- 页签 2：统计结果 -->
    <section v-else-if="activeTab === 'result'" class="rst-pane">
      <div class="rst-sub-tabs" role="tablist">
        <button
          v-for="sub in RESULT_SUB_TABS"
          :key="sub.value"
          class="rst-sub-tab"
          :class="{ active: resultSubTab === sub.value }"
          @click="resultSubTab = sub.value"
        >
          {{ sub.label }}
        </button>
      </div>

      <div v-if="statisticsLoading" class="rst-loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <p>正在统计分析...</p>
      </div>
      <div v-else-if="statisticsError" class="rst-error-state">
        <i class="fas fa-exclamation-circle"></i>
        <p>{{ statisticsError }}</p>
        <button class="btn btn-secondary btn-sm" @click="handleExecute">
          <i class="fas fa-redo"></i> 重试
        </button>
      </div>
      <template v-else-if="statisticsData">
        <!-- 概览 -->
        <div v-if="resultSubTab === 'overview'" class="rst-overview-grid">
          <div v-for="item in overviewItems" :key="item.label" class="card rst-overview-card">
            <span class="rst-overview-label">{{ item.label }}</span>
            <span class="rst-overview-value">{{ item.value }}</span>
          </div>
        </div>

        <!-- 详细 -->
        <div v-else-if="resultSubTab === 'detail'">
          <div v-if="detailColumns.length" class="rst-table-wrap">
            <table class="rst-table">
              <thead>
                <tr>
                  <th v-for="col in detailColumns" :key="col.key">{{ col.label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in statisticsData.detail" :key="idx">
                  <td v-for="col in detailColumns" :key="col.key">{{ formatDetailValue(row, col.key) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="rst-empty-state">
            <i class="fas fa-table"></i>
            <p>暂无明细数据</p>
          </div>
        </div>

        <!-- 图表 -->
        <div v-else-if="resultSubTab === 'chart'">
          <div v-if="statisticsChartData.labels.length" class="rst-chart-box">
            <ChartComponent
              title="统计图表"
              type="line"
              :data="statisticsChartData"
              :height="320"
              :show-actions="false"
              :enable-zoom="false"
            />
          </div>
          <div v-else class="rst-empty-state">
            <i class="fas fa-chart-pie"></i>
            <p>暂无图表数据</p>
          </div>
        </div>

        <!-- 异常 -->
        <div v-else-if="resultSubTab === 'anomaly'">
          <div v-if="statisticsData.anomaly.length" class="rst-table-wrap">
            <table class="rst-table">
              <thead>
                <tr>
                  <th>异常类型</th>
                  <th>报告名称</th>
                  <th>报告 ID</th>
                  <th>说明</th>
                  <th>数值</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in statisticsData.anomaly" :key="idx">
                  <td><span class="rst-anomaly-badge" :class="`rst-anomaly-${item.type}`">{{ getAnomalyTypeLabel(item.type) }}</span></td>
                  <td>{{ item.reportName }}</td>
                  <td>{{ item.reportId }}</td>
                  <td>{{ item.message }}</td>
                  <td>{{ item.value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="rst-empty-state">
            <i class="fas fa-check-circle"></i>
            <p>暂无异常统计</p>
          </div>
        </div>
      </template>
      <div v-else class="rst-empty-state">
        <i class="fas fa-table"></i>
        <p>暂无统计数据，请先执行统计分析</p>
      </div>
    </section>

    <!-- 页签 3：趋势分析 -->
    <section v-else-if="activeTab === 'trend'" class="rst-pane">
      <div class="rst-trend-toolbar">
        <div class="rst-sub-tabs" role="tablist">
          <button
            v-for="sub in TREND_SUB_TABS"
            :key="sub.value"
            class="rst-sub-tab"
            :class="{ active: trendSubTab === sub.value }"
            @click="trendSubTab = sub.value"
          >
            {{ sub.label }}
          </button>
        </div>
        <button class="btn btn-primary btn-sm" @click="handleTrendExecute" :disabled="trendLoading">
          <i class="fas fa-play" :class="{ 'fa-spin': trendLoading }"></i> 执行趋势分析
        </button>
      </div>

      <div v-if="trendLoading" class="rst-loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <p>正在获取趋势数据...</p>
      </div>
      <div v-else-if="trendError" class="rst-error-state">
        <i class="fas fa-exclamation-circle"></i>
        <p>{{ trendError }}</p>
        <button class="btn btn-secondary btn-sm" @click="handleTrendExecute">
          <i class="fas fa-redo"></i> 重试
        </button>
      </div>
      <template v-else-if="trendData">
        <!-- 时间趋势 -->
        <div v-if="trendSubTab === 'time_trend'">
          <div v-if="timeTrendRows.length" class="rst-table-wrap">
            <table class="rst-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>报告数量</th>
                  <th>总用例数</th>
                  <th>通过率</th>
                  <th>总时长(s)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in timeTrendRows" :key="idx">
                  <td>{{ row.date }}</td>
                  <td>{{ row.reportCount }}</td>
                  <td>{{ row.totalCases }}</td>
                  <td>{{ row.passRate }}%</td>
                  <td>{{ row.duration }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="rst-empty-state">
            <i class="fas fa-chart-line"></i>
            <p>暂无时间趋势数据</p>
          </div>
        </div>

        <!-- 维度趋势 -->
        <div v-else-if="trendSubTab === 'dimension_trend'">
          <div v-if="dimensionTrendRows.length" class="rst-table-wrap">
            <table class="rst-table">
              <thead>
                <tr>
                  <th>评估指标</th>
                  <th>日期</th>
                  <th>得分</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in dimensionTrendRows" :key="idx">
                  <td>{{ row.metric }}</td>
                  <td>{{ row.date }}</td>
                  <td>{{ row.value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="rst-empty-state">
            <i class="fas fa-ruler"></i>
            <p>暂无维度趋势数据</p>
          </div>
        </div>

        <!-- 趋势图表 -->
        <div v-else-if="trendSubTab === 'trend_chart'">
          <div v-if="trendChartData.labels.length" class="rst-chart-box">
            <ChartComponent
              title="趋势图表"
              type="line"
              :data="trendChartData"
              :height="320"
              :show-actions="false"
              :enable-zoom="false"
            />
          </div>
          <div v-else class="rst-empty-state">
            <i class="fas fa-chart-line"></i>
            <p>暂无趋势图表数据</p>
          </div>
        </div>

        <!-- 预测分析 -->
        <div v-else-if="trendSubTab === 'forecast'">
          <div v-if="forecastChartData.labels.length" class="rst-chart-box">
            <ChartComponent
              title="报告数量预测（基于历史线性趋势）"
              type="line"
              :data="forecastChartData"
              :height="320"
              :show-actions="false"
              :enable-zoom="false"
            />
            <p class="rst-note">说明：预测为前端基于历史趋势的线性外推，仅供参考，不代表后端统计口径。</p>
          </div>
          <div v-else class="rst-empty-state">
            <i class="fas fa-chart-line"></i>
            <p>暂无预测数据，请先执行趋势分析</p>
          </div>
        </div>
      </template>
      <div v-else class="rst-empty-state">
        <i class="fas fa-chart-line"></i>
        <p>暂无趋势数据，请点击「执行趋势分析」</p>
      </div>
    </section>

    <!-- 页签 4：报表生成 -->
    <section v-else class="rst-pane">
      <div class="card rst-report-form">
        <div class="rst-control-row">
          <div class="rst-control-item">
            <label>报表类型：</label>
            <select class="rst-select" v-model="reportType">
              <option v-for="opt in REPORT_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="rst-control-item">
            <label>报表格式：</label>
            <select class="rst-select" v-model="reportFormat">
              <option v-for="opt in REPORT_FORMAT_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
        </div>
        <div class="rst-control-row">
          <div class="rst-control-item rst-content-item">
            <label>报表内容：</label>
            <textarea class="rst-textarea" v-model="reportContent" placeholder="请输入报表内容说明..." rows="3"></textarea>
          </div>
        </div>
        <div class="rst-control-row">
          <button class="btn btn-primary" @click="handleGenerateReport" :disabled="reportGenerating">
            <i class="fas fa-file-export" :class="{ 'fa-spin': reportGenerating }"></i> 生成报表
          </button>
        </div>
      </div>

      <div v-if="generatedReports.length" class="rst-section">
        <h4 class="rst-section-title">本会话生成记录</h4>
        <div class="rst-table-wrap">
          <table class="rst-table">
            <thead>
              <tr>
                <th>文件名</th>
                <th>格式</th>
                <th>生成时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(rec, idx) in generatedReports" :key="idx">
                <td>{{ rec.filename }}</td>
                <td>{{ getFormatLabel(rec.format) }}</td>
                <td>{{ rec.generatedAt }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="rst-empty-state">
        <i class="fas fa-file-export"></i>
        <p>暂无报表生成记录</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import ChartComponent from '@/components/report/ChartComponent.vue'
import {
  useReportStatistics,
  STATISTICS_TABS,
  DIMENSION_OPTIONS,
  RESULT_SUB_TABS,
  TREND_SUB_TABS,
  REPORT_TYPE_OPTIONS,
  REPORT_FORMAT_OPTIONS,
} from './reportStatistics'
import type { ReportStatisticsDetailItem } from '@/domain'
import type { ToastMessage } from '@/domain/model/ui'

const router = useRouter()

const {
  activeTab,
  dimension,
  startDate,
  endDate,
  resultSubTab,
  trendSubTab,
  reportType,
  reportFormat,
  reportContent,
  statisticsLoading,
  statisticsError,
  statisticsData,
  trendLoading,
  trendError,
  trendData,
  reportGenerating,
  generatedReports,
  handleTabChange,
  executeStatistics,
  executeTrend,
  generateReport,
} = useReportStatistics()

const toast = ref<ToastMessage | null>(null)

function showToast(type: ToastMessage['type'], message: string): void {
  toast.value = { type, message }
  setTimeout(() => {
    toast.value = null
  }, 3000)
}

const handleExecute = () => {
  executeStatistics(showToast)
}

const handleTrendExecute = () => {
  executeTrend(showToast)
}

const handleGenerateReport = () => {
  generateReport(showToast)
}

const goBack = () => {
  router.push('/report-center')
}

// ---- 统计结果 ----

const DIMENSION_LABEL: Record<string, string> = {
  time: '时间',
  task_type: '任务类型',
  device_type: '设备类型',
  evaluation_metric: '评估维度',
}

const getDimensionLabel = (value: string): string => DIMENSION_LABEL[value] || value

const getDimensionIcon = (value: string): string => {
  const icons: Record<string, string> = {
    time: 'fas fa-calendar-alt',
    task_type: 'fas fa-tasks',
    device_type: 'fas fa-headphones',
    evaluation_metric: 'fas fa-ruler',
  }
  return icons[value] || 'fas fa-chart-column'
}

const getDimensionDesc = (value: string): string => {
  const descs: Record<string, string> = {
    time: '按创建时间区间统计报告与用例执行数量',
    task_type: '按任务类型分组统计执行结果',
    device_type: '按被测设备/API 维度统计性能指标',
    evaluation_metric: '按评估维度统计指标得分与通过率',
  }
  return descs[value] || ''
}

/** 总览卡片（overview → 标签/数值） */
const overviewItems = computed(() => {
  const o = statisticsData.value?.overview
  if (!o) return []
  return [
    { label: '报告数量', value: o.reportCount },
    { label: '已完成报告', value: o.completedReports },
    { label: '总用例数', value: o.totalCases },
    { label: '完成用例数', value: o.completedCases },
    { label: '失败用例数', value: o.failedCases },
    { label: '通过率', value: `${o.passRate}%` },
    { label: '总时长', value: `${o.duration}s` },
  ]
})

/** 明细表列定义（按首行实际字段动态生成，去空值列） */
const DETAIL_COLUMN_LABELS: Record<string, string> = {
  group: '分组',
  metric: '评估指标',
  deviceType: '设备类型',
  deviceCount: '设备数',
  reportCount: '报告数量',
  completedReports: '已完成',
  totalCases: '总用例数',
  completedCases: '完成用例数',
  failedCases: '失败用例数',
  passRate: '通过率',
  duration: '总时长(s)',
  averageValue: '平均得分',
  min: '最低',
  max: '最高',
}

const detailColumns = computed(() => {
  const rows = statisticsData.value?.detail
  if (!rows || rows.length === 0) return [] as Array<{ key: string; label: string }>
  const first = rows[0] as unknown as Record<string, unknown>
  return Object.keys(first)
    .filter(k => first[k] !== undefined && first[k] !== null)
    .map(k => ({ key: k, label: DETAIL_COLUMN_LABELS[k] || k }))
})

const formatDetailValue = (row: ReportStatisticsDetailItem, key: string): string | number => {
  const v = (row as unknown as Record<string, unknown>)[key]
  if (v === undefined || v === null) return '—'
  if (key === 'passRate') return `${v}%`
  if (key === 'duration') return `${v}s`
  return v as string | number
}

/** 异常类型中文名 */
const ANOMALY_TYPE_LABEL: Record<string, string> = {
  no_cases: '无用例数据',
  low_pass_rate: '通过率偏低',
  data_error: '数据异常',
}

const getAnomalyTypeLabel = (type: string): string => ANOMALY_TYPE_LABEL[type] || type

// ---- 统计图表 ----

/** 统计结果 chart（后端 categories+series）→ Chart.js 数据源 */
const statisticsChartData = computed(() => {
  const chart = statisticsData.value?.chart
  if (!chart || !chart.categories.length) return { labels: [], datasets: [] }
  return {
    labels: chart.categories,
    datasets: chart.series.map(s => ({
      label: s.name,
      data: s.data,
    })),
  }
})

// ---- 趋势分析 ----

const timeTrendRows = computed(() => trendData.value?.timeTrend ?? [])

const dimensionTrendRows = computed(() => {
  const rows: Array<{ metric: string; date: string; value: number }> = []
  for (const item of trendData.value?.dimensionTrend ?? []) {
    for (const p of item.points) {
      rows.push({ metric: item.metric, date: p.date, value: p.value })
    }
  }
  return rows
})

/** 趋势图表：优先时间趋势，无则回退维度趋势（首条指标序列） */
const trendChartData = computed(() => {
  const trend = trendData.value
  if (!trend) return { labels: [], datasets: [] }
  const tt = trend.timeTrend
  if (tt && tt.length) {
    return {
      labels: tt.map(t => t.date),
      datasets: [
        { label: '报告数量', data: tt.map(t => t.reportCount) },
        { label: '总用例数', data: tt.map(t => t.totalCases) },
        { label: '通过率', data: tt.map(t => t.passRate) },
      ],
    }
  }
  const dt = trend.dimensionTrend
  if (dt && dt.length) {
    return {
      labels: dt[0].points.map(p => p.date),
      datasets: dt.map(item => ({ label: item.metric, data: item.points.map(p => p.value) })),
    }
  }
  return { labels: [], datasets: [] }
})

/** 预测分析：对时间趋势报告数量做线性外推（前端呈现，虚线区分历史/预测） */
const forecastChartData = computed(() => {
  const points = trendData.value?.timeTrend ?? []
  if (!points.length) return { labels: [], datasets: [] }
  const n = points.length
  const xs = points.map((_, i) => i)
  const ys = points.map(p => p.reportCount)
  const sumX = xs.reduce((a, b) => a + b, 0)
  const sumY = ys.reduce((a, b) => a + b, 0)
  const sumXX = xs.reduce((a, b) => a + b * b, 0)
  const sumXY = xs.reduce((a, _, i) => a + xs[i] * ys[i], 0)
  const denom = n * sumXX - sumX * sumX
  const slope = denom !== 0 ? (n * sumXY - sumX * sumY) / denom : 0
  const intercept = denom !== 0 ? (sumY - slope * sumX) / n : n > 0 ? sumY / n : 0

  const labels = points.map(p => p.date)
  const hist = ys.map(y => Math.round(y * 10) / 10)
  const last = new Date(points[n - 1].date)
  const projLabels: string[] = []
  const projVals: number[] = []
  for (let i = 1; i <= 5; i++) {
    const d = new Date(last)
    d.setDate(d.getDate() + i)
    projLabels.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
    const x = n - 1 + i
    projVals.push(Math.max(0, Math.round((slope * x + intercept) * 10) / 10))
  }
  return {
    labels: [...labels, ...projLabels],
    datasets: [
      { label: '报告数量（历史）', data: hist },
      { label: '报告数量（预测）', data: [...Array(n).fill(null), ...projVals], borderDash: [6, 4] },
    ],
  }
})

// ---- 报表格式标签 ----

const FORMAT_LABEL: Record<string, string> = {
  csv: 'CSV',
  excel: 'Excel',
  pdf: 'PDF',
  html: 'HTML',
}

const getFormatLabel = (format: string): string => FORMAT_LABEL[format] || format

// ---- 自动触发 ----

// 进入趋势页签且尚未拉取过 → 自动执行（错误态由手动按钮重试）
watch(activeTab, (tab) => {
  if (tab === 'trend' && !trendData.value && !trendLoading.value && !trendError.value) {
    executeTrend(showToast)
  }
})

// 趋势子页签切换 → 数据与子页签口径不一致时按当前口径重新拉取
watch(trendSubTab, () => {
  const want = trendSubTab.value === 'dimension_trend' ? 'dimension' : 'time'
  if (trendData.value && trendData.value.trendType !== want && !trendLoading.value) {
    executeTrend(showToast)
  }
})
</script>

<style scoped>
.rst-statistics-view {
  padding: var(--spacing-lg);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: var(--spacing-lg);
}

.page-title {
  margin: 0;
  font-size: var(--font-size-xl);
}

.page-description {
  margin: var(--spacing-xs) 0 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

/* ===== 控制区 ===== */
.rst-control-section {
  padding: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.rst-control-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-sm);
}

.rst-control-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.rst-control-item label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  white-space: nowrap;
}

.rst-select {
  border: 2px solid var(--color-gray-300) !important;
  background-color: var(--background-primary) !important;
  border-radius: var(--border-radius-md) !important;
  padding: var(--spacing-sm) var(--spacing-md) !important;
  font-size: var(--font-size-sm) !important;
  color: var(--text-primary) !important;
}

.date-input {
  border: 2px solid var(--color-gray-300) !important;
  background-color: var(--background-primary) !important;
  border-radius: var(--border-radius-md) !important;
  padding: var(--spacing-xs) var(--spacing-sm) !important;
  font-size: var(--font-size-sm) !important;
  color: var(--text-primary) !important;
}

.rst-content-item {
  flex: 1;
  min-width: 320px;
  align-items: flex-start;
}

.rst-textarea {
  flex: 1;
  border: 2px solid var(--color-gray-300);
  border-radius: var(--border-radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  background-color: var(--background-primary);
  resize: vertical;
  width: 100%;
}

.rst-textarea:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-light);
  outline: none;
}

/* ===== 四页签 ===== */
.rst-tabs {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-sm);
  background: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  border: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.rst-tab {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border: 1px solid transparent;
  border-radius: var(--border-radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.rst-tab:hover {
  background: var(--background-primary);
  color: var(--primary-color);
}

.rst-tab.active {
  background: var(--primary-color);
  color: var(--color-white);
  border-color: var(--primary-color);
  box-shadow: var(--shadow-sm);
}

/* ===== 子页签 ===== */
.rst-sub-tabs {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.rst-sub-tab {
  padding: var(--spacing-xs) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-full);
  background: var(--background-primary);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.2s ease;
}

.rst-sub-tab:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.rst-sub-tab.active {
  background: var(--primary-color);
  color: var(--color-white);
  border-color: var(--primary-color);
}

/* ===== 趋势工具栏 ===== */
.rst-trend-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
  flex-wrap: wrap;
}

/* ===== 页签内容 ===== */
.rst-pane {
  min-height: 240px;
}

.rst-sub-description {
  margin-bottom: var(--spacing-lg);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.rst-dimension-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.rst-dimension-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  background: var(--background-primary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.rst-dimension-card:hover {
  border-color: var(--primary-color);
  box-shadow: var(--shadow-md);
}

.rst-dimension-card--active {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px var(--primary-light);
}

.rst-dimension-card i {
  font-size: 1.2rem;
  color: var(--primary-color);
}

.rst-dimension-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.rst-dimension-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

/* ===== 分区标题 ===== */
.rst-section {
  margin-top: var(--spacing-md);
}

.rst-section-title {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-md);
  color: var(--text-primary);
}

/* ===== 总览卡片 ===== */
.rst-overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.rst-overview-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--spacing-md);
  border-radius: var(--border-radius-lg);
  background: var(--background-primary);
  border: 1px solid var(--border-color);
}

.rst-overview-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.rst-overview-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--primary-color);
}

/* ===== 表格 ===== */
.rst-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  background: var(--background-primary);
}

.rst-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.rst-table th,
.rst-table td {
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--border-color);
  text-align: left;
  white-space: nowrap;
}

.rst-table th {
  background: var(--background-secondary);
  color: var(--text-secondary);
  font-weight: var(--font-weight-semibold);
}

.rst-table tbody tr:hover {
  background: var(--background-secondary);
}

.rst-table tbody tr:last-child td {
  border-bottom: none;
}

/* ===== 异常徽标 ===== */
.rst-anomaly-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--border-radius-full);
  font-size: var(--font-size-sm);
}

.rst-anomaly-no_cases {
  background: var(--color-amber-50);
  color: var(--color-amber-600);
}

.rst-anomaly-low_pass_rate {
  background: var(--color-red-50);
  color: var(--color-red-600);
}

.rst-anomaly-data_error {
  background: var(--color-purple-50, var(--color-blue-50));
  color: var(--color-purple-600, var(--color-blue-600));
}

/* ===== 图表 ===== */
.rst-chart-box {
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  background: var(--background-primary);
  padding: var(--spacing-lg);
}

.rst-note {
  margin: var(--spacing-sm) 0 0 0;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ===== 加载 / 错误 / 空态 ===== */
.rst-loading-state,
.rst-error-state,
.rst-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--spacing-xxl);
  color: var(--text-tertiary);
  gap: var(--spacing-sm);
}

.rst-loading-state i,
.rst-error-state i,
.rst-empty-state i {
  font-size: var(--font-size-xxxl);
  margin-bottom: var(--spacing-sm);
  color: var(--text-disabled);
}

.rst-error-state {
  color: var(--color-red-600);
}

.rst-error-state i {
  color: var(--color-red-600);
}

.rst-loading-state p,
.rst-error-state p,
.rst-empty-state p {
  margin: 0;
  font-size: var(--font-size-md);
}

/* ===== 报表表单 ===== */
.rst-report-form {
  padding: var(--spacing-lg);
  margin-bottom: var(--spacing-md);
}

/* ===== Toast ===== */
.rst-toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 10000;
  animation: rst-slide-in 0.3s ease;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--color-black) 15%, transparent);
}

.rst-toast-container i {
  font-size: 1.2rem;
}

.rst-toast-success { background-color: var(--color-green-50); color: var(--color-green-600); border: 1px solid var(--color-green-600); }
.rst-toast-error { background-color: var(--color-red-50); color: var(--color-red-600); border: 1px solid var(--color-red-600); }
.rst-toast-warning { background-color: var(--color-amber-50); color: var(--color-amber-600); border: 1px solid var(--color-amber-600); }
.rst-toast-info { background-color: var(--color-blue-50); color: var(--color-blue-600); border: 1px solid var(--color-blue-600); }

@keyframes rst-slide-in {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
</style>
