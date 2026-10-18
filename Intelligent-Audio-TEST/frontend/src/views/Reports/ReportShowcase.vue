<template>
  <div class="rs-showcase-view">
    <!-- Toast 提示：Teleport 到全局固定元素容器 -->
    <teleport to="#global-fixed-elements">
      <div v-if="toast" class="rs-toast-container" :class="`rs-toast-${toast.type}`">
        <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : toast.type === 'warning' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle'"></i>
        <span>{{ toast.message }}</span>
      </div>
    </teleport>

    <!-- 页面标题 -->
    <div class="page-header rs-page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-file-alt"></i>
          报告
        </h2>
        <p class="page-description">浏览已发布的测试报告，可按算法、类型与时间检索</p>
      </div>
    </div>

    <!-- 算法卡片网格（本页不渲染右上角算法切换器，页内每算法一张大卡） -->
    <section class="card rs-algorithm-section">
      <div class="rs-section-head">
        <h3 class="rs-section-title">
          <i class="fas fa-microchip"></i>
          选择算法
        </h3>
        <p class="rs-section-sub">点击卡片切换算法，报告列表将按此算法过滤</p>
      </div>
      <div class="rs-algorithm-grid">
        <button
          type="button"
          class="rs-algorithm-card"
          :class="{ 'rs-algorithm-card--active': isAlgorithmSelected('all') }"
          @click="selectAlgorithm('all')"
        >
          <i class="fas fa-layer-group rs-algo-icon"></i>
          <span class="rs-algo-name">全部算法</span>
          <span class="rs-algo-desc">当前未按算法筛选，展示全部算法的已发布报告。</span>
        </button>
        <button
          v-for="algo in algorithms"
          :key="algo.type"
          type="button"
          class="rs-algorithm-card"
          :class="{ 'rs-algorithm-card--active': isAlgorithmSelected(algo.type) }"
          @click="selectAlgorithm(algo.type)"
        >
          <div class="rs-algo-head">
            <span class="rs-algo-name">{{ algo.name || algo.type }}</span>
            <span v-if="algo.groupName" class="rs-algo-group">{{ algo.groupName }}</span>
            <span class="rs-algo-status" :class="algo.status === 'online' ? 'rs-algo-status--online' : 'rs-algo-status--offline'">
              {{ algo.status === 'online' ? '在线' : '离线' }}
            </span>
          </div>
          <span class="rs-algo-desc">{{ algo.description || '暂无算法描述' }}</span>
        </button>
      </div>
      <div v-if="algorithmError" class="rs-algo-error">
        <i class="fas fa-exclamation-triangle"></i> {{ algorithmError }}
      </div>
    </section>

    <!-- 筛选栏 -->
    <section class="rs-filter-section">
      <div class="rs-filter-row">
        <div class="rs-filter-item rs-search-filter">
          <label>搜索报告：</label>
          <input
            type="text"
            class="search-input"
            placeholder="搜索报告名称、任务或算法..."
            v-model="search"
            @input="handleSearchInput"
          />
        </div>
        <BadgeFilter
          :options="REPORT_TYPE_OPTIONS"
          :model-value="reportType"
          all-label="全部"
          title="报告类型"
          @update:model-value="handleTypeFilterChange"
        />
        <BadgeFilter
          :options="TIME_RANGE_OPTIONS"
          :model-value="timeRange"
          all-label="全部时间"
          title="时间范围"
          @update:model-value="handleTimeRangeChange"
        />
      </div>
      <div class="rs-filter-row" v-if="timeRange === 'custom'">
        <div class="rs-filter-item rs-custom-time-range">
          <div>
            <label for="rs-start-date">开始:</label>
            <input type="date" id="rs-start-date" class="date-input" v-model="startDate" @change="handleFilterChange" />
          </div>
          <span>至</span>
          <div>
            <label for="rs-end-date">结束:</label>
            <input type="date" id="rs-end-date" class="date-input" v-model="endDate" @change="handleFilterChange" />
          </div>
          <button class="btn btn-secondary" @click="clearDateRange">
            <i class="fas fa-times"></i> 清除
          </button>
        </div>
      </div>
      <div class="rs-filter-row rs-sort-row">
        <div class="rs-sort-options">
          <span>排序：</span>
          <div class="rs-sort-item" :class="{ active: sort.sortBy === 'createdAt' }" @click="handleSortChange('createdAt')">
            创建时间
            <i class="fas fa-sort-down" v-if="sort.sortBy === 'createdAt' && sort.order === 'desc'"></i>
            <i class="fas fa-sort-up" v-else-if="sort.sortBy === 'createdAt' && sort.order === 'asc'"></i>
            <i class="fas fa-sort" v-else></i>
          </div>
          <div class="rs-sort-item" :class="{ active: sort.sortBy === 'name' }" @click="handleSortChange('name')">
            报告名称
            <i class="fas fa-sort-down" v-if="sort.sortBy === 'name' && sort.order === 'desc'"></i>
            <i class="fas fa-sort-up" v-else-if="sort.sortBy === 'name' && sort.order === 'asc'"></i>
            <i class="fas fa-sort" v-else></i>
          </div>
          <div class="rs-sort-item" :class="{ active: sort.sortBy === 'status' }" @click="handleSortChange('status')">
            状态
            <i class="fas fa-sort-down" v-if="sort.sortBy === 'status' && sort.order === 'desc'"></i>
            <i class="fas fa-sort-up" v-else-if="sort.sortBy === 'status' && sort.order === 'asc'"></i>
            <i class="fas fa-sort" v-else></i>
          </div>
        </div>
      </div>
    </section>

    <!-- 工具栏 -->
    <div class="rs-toolbar">
      <span class="rs-toolbar-count">共 {{ totalItems }} 个已发布报告</span>
      <span class="rs-toolbar-hint">管理操作请前往报告中心</span>
    </div>

    <!-- 加载指示 -->
    <div v-if="loading" class="rs-loading-bar">
      <span class="rs-loading-spinner"></span>
      正在加载报告...
    </div>

    <!-- 报告列表（卡片视图，行操作仅查看/复制链接） -->
    <div v-for="report in reports" :key="report.id" class="card rs-report-card">
      <div class="card-header">
        <div class="rs-report-card-title-wrapper">
          <h3 class="rs-report-card-title">{{ report.name }}</h3>
          <div class="rs-report-card-meta-tags">
            <span class="rs-report-card-type">{{ getReportTypeLabel(report.type) }}</span>
            <span class="rs-report-card-status rs-report-card-status--published">已发布</span>
            <VisibilityBadge :visibility="report.visibility" />
            <span v-if="report.algorithmType" class="rs-report-card-algorithm-type">{{ getAlgorithmLabel(report.algorithmType) }}</span>
            <span v-if="report.taskName" class="rs-report-card-task-name">{{ report.taskName }}</span>
          </div>
        </div>
        <div class="rs-card-actions">
          <button class="btn btn-primary" @click="viewReport(report.id)">
            <i class="fas fa-eye"></i> 查看
          </button>
          <button class="btn btn-secondary" @click="copyReportLink(report)">
            <i class="fas fa-link"></i> 复制链接
          </button>
        </div>
      </div>
      <div class="card-body">
        <p class="rs-report-card-description">{{ report.description || getReportSummary(report) }}</p>
        <div class="rs-report-card-meta">
          <span class="rs-report-card-meta-item">
            <i class="fas fa-calendar-alt"></i>
            {{ formatDate(report.createdAt) }}
          </span>
          <template v-if="report.type === 'comparison' || report.type === 'secondary_comparison'">
            <span class="rs-report-card-meta-item">
              <i class="fas fa-cubes"></i>
              {{ report.summary?.taskCount || 0 }} 个任务对比
            </span>
          </template>
          <template v-else-if="report.type !== 'benchmark'">
            <span class="rs-report-card-meta-item">
              <i class="fas fa-list-check"></i>
              {{ report.summary?.totalCases || 0 }} 个测试用例
            </span>
            <span class="rs-report-card-meta-item">
              <i class="fas fa-check-circle"></i>
              {{ report.summary?.overallSuccessRate || report.summary?.passRate || 0 }}% 通过率
            </span>
          </template>
          <template v-else>
            <span class="rs-report-card-meta-item">
              <i class="fas fa-trophy"></i>
              排行快照报告
            </span>
          </template>
        </div>
      </div>
    </div>

    <!-- 空态 -->
    <div v-if="!loading && reports.length === 0" class="rs-no-data">
      <i class="fas fa-inbox"></i>
      <p>暂无已发布报告</p>
    </div>

    <!-- 分页 -->
    <PaginationComponent
      :current-page="currentPage"
      :page-size="pageSize"
      :total-items="totalItems"
      @prev-page="handlePrevPage"
      @next-page="handleNextPage"
      @go-to-page="handleGoToPage"
      @page-size-change="handlePageSizeChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BadgeFilter from '../../components/common/BadgeFilter.vue'
import VisibilityBadge from '../../components/common/visibility/VisibilityBadge.vue'
import PaginationComponent from '../../components/common/data/PaginationComponent.vue'
import { useReportShowcase } from './reportShowcase'
import { useAlgorithmLabels } from '../../composables/algorithm/useAlgorithmLabels'

const REPORT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'task', label: '任务报告' },
  { value: 'comparison', label: '对比报告' },
  { value: 'secondary_comparison', label: '二次对比报告' },
  { value: 'benchmark', label: 'Benchmark 报告' },
]

/** 时间范围选项（可变数组，适配 BadgeFilter 单选项契约；'all' 由「全部时间」徽章承担） */
const TIME_RANGE_OPTIONS: { value: string; label: string }[] = [
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
]

const {
  algorithms,
  selectedAlgorithm,
  loadingAlgorithms,
  algorithmError,
  selectAlgorithm,
  isAlgorithmSelected,
  reports,
  totalItems,
  currentPage,
  pageSize,
  loading,
  search,
  reportType,
  timeRange,
  startDate,
  endDate,
  sort,
  toast,
  handleSearchInput,
  handleTypeFilterChange,
  handleTimeRangeChange,
  handleFilterChange,
  clearDateRange,
  handleSortChange,
  viewReport,
  copyReportLink,
  handlePrevPage,
  handleNextPage,
  handleGoToPage,
  handlePageSizeChange,
  totalPages,
  getReportTypeLabel,
  formatDate,
} = useReportShowcase()

// 算法标签（复用全局算法选项做 value→中文名映射；接口为空兜底内置清单）
const { getAlgorithmLabel } = useAlgorithmLabels()

/** 报告摘要（复用 HistoryReports 口径：task/comparison/benchmark 分型文案） */
function getReportSummary(report: any): string {
  if (!report.summary) return '暂无摘要'
  const summary = report.summary
  const totalCases = summary.totalCases || 0
  const completedCases = summary.completedCases || summary.completed_cases || 0
  const failedCases = summary.failedCases || summary.failed_cases || 0
  const successRate = summary.overallSuccessRate || summary.passRate || 0
  if (report.type === 'comparison' || report.type === 'secondary_comparison') {
    return `共对比 ${summary.taskCount || 0} 个任务，包含 ${totalCases} 个测试用例`
  }
  if (report.type === 'benchmark') {
    return `Benchmark 排行快照报告（发布时点定格，点击查看详情）`
  }
  return `共 ${totalCases} 个测试用例，通过 ${completedCases} 个，失败 ${failedCases} 个，通过率 ${successRate}%`
}
</script>

<style scoped>
.rs-showcase-view {
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

/* ===== 算法卡片网格 ===== */
.rs-algorithm-section {
  padding: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.rs-section-head {
  margin-bottom: var(--spacing-md);
}

.rs-section-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.rs-section-title i {
  color: var(--primary-color);
  font-size: 1rem;
}

.rs-section-sub {
  margin: var(--spacing-xs) 0 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.rs-algorithm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--spacing-md);
}

.rs-algorithm-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  background: var(--background-primary);
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  align-items: flex-start;
}

.rs-algorithm-card:hover {
  border-color: var(--primary-color);
  box-shadow: var(--shadow-md);
}

.rs-algorithm-card--active {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px var(--primary-light);
  background: var(--primary-light);
}

.rs-algo-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rs-algo-icon {
  font-size: 1.2rem;
  color: var(--primary-color);
}

.rs-algo-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.rs-algo-group {
  font-size: var(--font-size-xs);
  padding: 1px 8px;
  border-radius: var(--border-radius-sm);
  background: var(--secondary-light);
  color: var(--secondary-color);
}

.rs-algo-status {
  font-size: var(--font-size-xs);
  padding: 1px 8px;
  border-radius: var(--border-radius-sm);
  font-weight: var(--font-weight-medium);
}

.rs-algo-status--online {
  background: var(--success-light);
  color: var(--success-dark);
}

.rs-algo-status--offline {
  background: var(--muted);
  color: var(--text-tertiary);
}

.rs-algo-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.rs-algo-error {
  margin-top: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--border-radius-sm);
  background: var(--warning-light);
  color: var(--warning-color);
  font-size: var(--font-size-sm);
}

/* ===== 筛选栏 ===== */
.rs-filter-section {
  margin-bottom: var(--spacing-md);
}

.rs-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
}

.rs-filter-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.rs-filter-item label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  white-space: nowrap;
}

.rs-search-filter {
  flex: 1;
  min-width: 260px;
}

.rs-search-filter :deep(.search-input) {
  border: 2px solid var(--color-gray-300) !important;
  background-color: var(--background-primary) !important;
  border-radius: var(--border-radius-lg) !important;
  padding: var(--spacing-sm) var(--spacing-md) !important;
  font-size: var(--font-size-md) !important;
  color: var(--text-primary) !important;
  width: 100%;
}

.rs-search-filter :deep(.search-input:focus) {
  border-color: var(--primary-color) !important;
  box-shadow: 0 0 0 3px var(--primary-light) !important;
}

.rs-custom-time-range {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.rs-custom-time-range .date-input {
  border: 2px solid var(--color-gray-300) !important;
  background-color: var(--background-primary) !important;
  border-radius: var(--border-radius-md) !important;
  padding: var(--spacing-xs) var(--spacing-sm) !important;
  font-size: var(--font-size-sm) !important;
  color: var(--text-primary) !important;
}

.rs-sort-row {
  justify-content: flex-end;
}

.rs-sort-options {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.rs-sort-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--border-radius-sm);
  user-select: none;
}

.rs-sort-item.active {
  color: var(--primary-color);
  font-weight: var(--font-weight-semibold);
}

/* ===== 工具栏 ===== */
.rs-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--border-color);
}

.rs-toolbar-count {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: var(--font-weight-semibold);
}

.rs-toolbar-hint {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

/* ===== 加载 / 空态 ===== */
.rs-loading-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: var(--spacing-md);
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
  border-radius: var(--border-radius-lg);
  color: var(--text-secondary);
  font-size: 14px;
}

.rs-loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: rs-spin 0.8s linear infinite;
}

@keyframes rs-spin {
  to { transform: rotate(360deg); }
}

.rs-no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--spacing-xxl);
  color: var(--text-tertiary);
}

.rs-no-data i {
  font-size: var(--font-size-xxxl);
  margin-bottom: var(--spacing-lg);
  color: var(--text-disabled);
}

.rs-no-data p {
  margin: 0;
  font-size: var(--font-size-md);
}

/* ===== 报告卡片 ===== */
.rs-report-card {
  border: var(--card-border);
  border-radius: var(--border-radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
  background-color: var(--background-primary);
}

.rs-report-card .card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-sm);
  border-bottom: none;
  background: transparent;
}

.rs-report-card-title-wrapper {
  flex: 1;
  min-width: 0;
}

.rs-report-card-title {
  margin: 0 0 var(--spacing-xs) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.rs-report-card-meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  align-items: center;
}

.rs-report-card-type,
.rs-report-card-status,
.rs-report-card-task-name,
.rs-report-card-algorithm-type {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--border-radius-sm);
  background-color: var(--info-light);
  color: var(--info-color);
}

.rs-report-card-status--published {
  background-color: var(--success-light);
  color: var(--success-dark);
}

.rs-report-card-algorithm-type {
  background-color: var(--color-sky-50);
  color: var(--color-sky-600);
}

.rs-report-card-task-name {
  background-color: var(--primary-light);
  color: var(--primary-color);
}

.rs-card-actions {
  display: flex;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

.rs-report-card-description {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  margin: 0 0 var(--spacing-sm) 0;
}

.rs-report-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.rs-report-card-meta-item {
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.rs-report-card-meta-item i {
  color: var(--primary-color);
}

/* ===== Toast ===== */
.rs-toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 10000;
  animation: rs-slide-in 0.3s ease;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--color-black) 15%, transparent);
}

.rs-toast-container i {
  font-size: 1.2rem;
}

.rs-toast-success { background-color: var(--color-green-50); color: var(--color-green-600); border: 1px solid var(--color-green-600); }
.rs-toast-error { background-color: var(--color-red-50); color: var(--color-red-600); border: 1px solid var(--color-red-600); }
.rs-toast-warning { background-color: var(--color-amber-50); color: var(--color-amber-600); border: 1px solid var(--color-amber-600); }
.rs-toast-info { background-color: var(--color-blue-50); color: var(--color-blue-600); border: 1px solid var(--color-blue-600); }

@keyframes rs-slide-in {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
</style>
