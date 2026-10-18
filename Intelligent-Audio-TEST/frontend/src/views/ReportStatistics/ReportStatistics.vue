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

    <!-- 待后端立项提示条（G04 出壳：不造数据兜底） -->
    <div class="rst-pending-banner">
      <i class="fas fa-info-circle"></i>
      <span>{{ pendingNotice }}</span>
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
          <button class="btn btn-primary" @click="handleExecute">
            <i class="fas fa-play"></i> 执行统计分析
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
      <div class="rst-empty-state">
        <i class="fas fa-chart-column"></i>
        <p>暂无统计数据</p>
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
      <div class="rst-empty-state">
        <i class="fas fa-table"></i>
        <p>暂无统计数据</p>
      </div>
    </section>

    <!-- 页签 3：趋势分析 -->
    <section v-else-if="activeTab === 'trend'" class="rst-pane">
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
      <div class="rst-empty-state">
        <i class="fas fa-chart-line"></i>
        <p>暂无趋势数据</p>
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
          <button class="btn btn-primary" @click="handleExecute">
            <i class="fas fa-file-export"></i> 生成报表
          </button>
        </div>
      </div>
      <div class="rst-empty-state">
        <i class="fas fa-file-export"></i>
        <p>暂无报表生成记录</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  useReportStatistics,
  STATISTICS_TABS,
  DIMENSION_OPTIONS,
  RESULT_SUB_TABS,
  TREND_SUB_TABS,
  REPORT_TYPE_OPTIONS,
  REPORT_FORMAT_OPTIONS,
} from './reportStatistics'
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
  pendingNotice,
  handleTabChange,
  executeStatistics,
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

const goBack = () => {
  router.push('/report-center')
}

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

/* ===== 待后端立项提示条 ===== */
.rst-pending-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: var(--spacing-lg);
  border-radius: var(--border-radius-lg);
  background: var(--warning-light);
  color: var(--warning-dark);
  font-size: 14px;
  border: 1px solid var(--warning-color);
}

.rst-pending-banner i {
  font-size: 1.1rem;
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
  margin-bottom: var(--spacing-lg);
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

/* ===== 空态 ===== */
.rst-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--spacing-xxl);
  color: var(--text-tertiary);
}

.rst-empty-state i {
  font-size: var(--font-size-xxxl);
  margin-bottom: var(--spacing-lg);
  color: var(--text-disabled);
}

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
