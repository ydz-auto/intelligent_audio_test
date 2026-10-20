<template>
  <div class="rc-report-center-view">
    <!-- Toast 提示：公共组件（样式走 token，INT-969） -->
    <Toast :toast="toast" />

    <!-- 页面标题 -->
    <div class="page-header rc-page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-file-invoice"></i>
          报告中心
        </h2>
        <p class="page-description">生成、编辑、发布、删除、批量、导出、收藏、回收站等报告管理操作集中于此</p>
      </div>
      <div class="header-actions">
        <!-- G04：统计分析入口（report:read） -->
        <button class="btn btn-secondary" @click="goStatistics">
          <i class="fas fa-chart-line"></i> 统计分析
        </button>
        <!-- INT-483：发布 Benchmark 报告入口（权限 benchmark:report:publish 显隐） -->
        <button v-if="canPublishBenchmarkReport" class="btn btn-primary benchmark-publish-btn" @click="openBenchmarkPublish">
          <i class="fas fa-trophy"></i> 发布 Benchmark 报告
        </button>
      </div>
    </div>

    <!-- 统计徽章行（GET /reports/tab-counts；点击=快速筛选，非页签层级） -->
    <div class="rc-stats-row">
      <button
        v-for="badge in STAT_BADGES"
        :key="badge.key"
        class="rc-stat-badge card"
        :class="{ 'rc-stat-badge--active': isStatActive(badge.key) }"
        @click="handleStatBadgeClick(badge.key)"
      >
        <span class="rc-stat-icon" :class="badge.iconClass">
          <i :class="badge.icon"></i>
        </span>
        <span class="rc-stat-info">
          <span class="rc-stat-label">{{ badge.label }}</span>
          <span class="rc-stat-count">{{ getStatCount(badge.key) }}</span>
        </span>
      </button>
    </div>

    <!-- 筛选和排序栏 -->
    <section class="filter-sort-section">
      <div class="rc-filter-row">
        <div class="rc-filter-item rc-search-filter">
          <label>搜索报告：</label>
          <input
            type="text"
            class="search-input"
            placeholder="搜索报告名称、创建时间..."
            v-model="filters.search"
            @input="handleFilterChange"
          />
        </div>

        <!-- 类型 = 筛选条件（单选，非页签层级；默认「全部」） -->
        <BadgeFilter
          :options="REPORT_TYPE_OPTIONS"
          :model-value="filters.reportType"
          all-label="全部类型"
          title="报告类型"
          @update:model-value="handleReportTypeFilterChange"
        />

        <BadgeFilter
          :options="REPORT_STATUS_OPTIONS"
          :model-value="filters.reportStatus"
          all-label="全部状态"
          title="报告状态"
          @update:model-value="handleReportStatusFilterChange"
        />

        <BadgeFilter
          :options="TIME_RANGE_OPTIONS"
          :model-value="filters.timeRange"
          all-label="全部时间"
          title="时间范围"
          @update:model-value="handleTimeRangeFilterChange"
        />
      </div>

      <div class="rc-filter-row">
        <!-- 自定义时间范围 -->
        <div class="rc-filter-item rc-custom-time-range" v-if="filters.timeRange === 'custom'">
          <div>
            <label for="rc-start-date">开始:</label>
            <input type="date" id="rc-start-date" class="date-input" v-model="filters.startDate" @change="handleFilterChange" />
          </div>
          <span>至</span>
          <div>
            <label for="rc-end-date">结束:</label>
            <input type="date" id="rc-end-date" class="date-input" v-model="filters.endDate" @change="handleFilterChange" />
          </div>
          <button class="btn btn-secondary" @click="clearDateRange">
            <i class="fas fa-times"></i> 清除
          </button>
        </div>

        <AlgorithmFilter
          :options="algorithmOptions"
          :model-value="filters.algorithmType"
          title="算法筛选"
          @update:model-value="handleAlgorithmFilterChange"
        />

        <!-- 可见性筛选（全部/共享/私有；服务端 ?visibility= 行级过滤） -->
        <BadgeFilter
          :options="VISIBILITY_FILTER_OPTIONS"
          :model-value="visibilityFilter || 'all'"
          all-label="全部"
          title="可见性"
          @update:model-value="handleVisibilityFilterChange"
        />

        <div class="rc-sort-options">
          <span>排序：</span>
          <div class="rc-sort-item" :class="{ active: sort.sortBy === 'createdAt' }" @click="handleSortChange('createdAt')">
            创建时间
            <i class="fas fa-sort-down" v-if="sort.sortBy === 'createdAt' && sort.order === 'desc'"></i>
            <i class="fas fa-sort-up" v-else-if="sort.sortBy === 'createdAt' && sort.order === 'asc'"></i>
            <i class="fas fa-sort" v-else></i>
          </div>
          <div class="rc-sort-item" :class="{ active: sort.sortBy === 'name' }" @click="handleSortChange('name')">
            报告名称
            <i class="fas fa-sort-down" v-if="sort.sortBy === 'name' && sort.order === 'desc'"></i>
            <i class="fas fa-sort-up" v-else-if="sort.sortBy === 'name' && sort.order === 'asc'"></i>
            <i class="fas fa-sort" v-else></i>
          </div>
        </div>
      </div>
    </section>

    <!-- 收藏 / 回收站工具栏 -->
    <FavoriteTrashBar
      :favorite-only="favoriteOnly"
      :trash-mode="trashMode"
      :favorite-disabled="trashMode"
      @update:favorite-only="handleReportFavoriteFilterChange"
      @update:trash-mode="toggleTrashMode"
    />

    <!-- 批量操作栏 -->
    <div class="rc-batch-actions" v-if="allReports.length > 0">
      <div class="rc-batch-select-all">
        <input type="checkbox" id="select-all-reports" class="task-checkbox" v-model="isAllSelected" @change="toggleSelectAll" />
        <label for="select-all-reports"></label>
        <span class="rc-select-all-label">全选</span>
      </div>
      <div v-if="selectedReports.size > 0" class="rc-batch-action-buttons">
        <template v-if="!trashMode">
          <button class="btn btn-success" @click="handleBatchCompare">
            <i class="fas fa-exchange-alt"></i> 批量对比
          </button>
          <button class="btn btn-danger" @click="handleBatchDelete">
            <i class="fas fa-trash"></i> 批量删除 ({{ selectedReports.size }})
          </button>
        </template>
        <template v-else>
          <button class="btn btn-success" @click="handleBatchRestore">
            <i class="fas fa-undo"></i> 批量恢复 ({{ selectedReports.size }})
          </button>
          <button class="btn btn-danger" @click="handleBatchPurge">
            <i class="fas fa-fire"></i> 批量彻底删除 ({{ selectedReports.size }})
          </button>
        </template>
        <button class="btn btn-secondary" @click="handleBatchCancel">
          <i class="fas fa-times"></i> 取消选择
        </button>
      </div>
    </div>

    <!-- 加载指示 -->
    <div v-if="loading" class="rc-loading-bar">
      <span class="rc-loading-spinner"></span>
      正在加载报告...
    </div>

    <!-- 报告列表：单一视图（类型=筛选条件，无页签分组） -->
    <div
      v-for="report in allReports"
      :key="report.id"
      class="card rc-report-card"
      :class="{ 'rc-card-selected': selectedReports.has(report.id) }"
      @click="toggleReportSelection(report.id, $event)"
    >
      <div class="card-header">
        <div class="rc-report-checkbox-wrapper">
          <input
            type="checkbox"
            class="task-checkbox"
            :id="`report-${report.id}`"
            :checked="selectedReports.has(report.id)"
            @change="selectedReports.has(report.id) ? selectedReports.delete(report.id) : selectedReports.add(report.id)"
            @click.stop
          />
          <label :for="`report-${report.id}`"></label>
        </div>
        <div class="rc-report-card-title-wrapper">
          <h3 class="rc-report-card-title">{{ report.name }}</h3>
          <div class="rc-report-card-meta-tags">
            <span class="rc-report-card-type">{{ getReportTypeLabel(report.type) }}</span>
            <span class="rc-report-card-status" :class="report.status === ReportStatus.DRAFT ? 'rc-status-draft' : 'rc-status-published'">
              {{ report.status === ReportStatus.DRAFT ? '草稿' : '已发布' }}
            </span>
            <VisibilityBadge :visibility="report.visibility" />
            <span v-if="report.algorithmType" class="rc-report-card-algorithm-type">{{ getAlgorithmTypeLabel(report.algorithmType) }}</span>
            <span v-if="report.taskName" class="rc-report-card-test-type">{{ report.taskName }}</span>
          </div>
        </div>
        <div class="card-actions">
          <template v-if="trashMode">
            <button class="btn btn-success" @click.stop="handleRestoreReport(report)">
              <i class="fas fa-undo"></i> 恢复
            </button>
            <button class="btn btn-danger" @click.stop="handlePurgeReport(report)">
              <i class="fas fa-fire"></i> 彻底删除
            </button>
          </template>
          <template v-else>
            <button class="btn btn-secondary" :title="isFavorite(report.id) ? '取消收藏' : '收藏'"
                    :style="isFavorite(report.id) ? 'color: var(--favorite-star)' : ''"
                    @click.stop="handleToggleFavorite(report)">
              <i :class="isFavorite(report.id) ? 'fas fa-star' : 'far fa-star'"></i>
            </button>
            <button class="btn btn-primary" @click.stop="viewReport(report.id, report.type)">
              <i class="fas fa-eye"></i> 查看
            </button>
            <button v-if="canEditResource(report)" class="btn btn-secondary" @click.stop="editReport(report.id)">
              <i class="fas fa-edit"></i> 编辑
            </button>
            <button v-if="canEditResource(report)" class="btn btn-danger" @click.stop="deleteReport(report.id)">
              <i class="fas fa-trash"></i> 删除
            </button>
            <button v-if="report.status === ReportStatus.DRAFT" class="btn btn-success" @click.stop="publishReport(report.id)">
              <i class="fas fa-paper-plane"></i> 发布
            </button>
          </template>
        </div>
      </div>
      <div class="card-body">
        <p class="rc-report-card-description">{{ report.description || getReportSummary(report) }}</p>
        <div class="rc-report-card-meta">
          <span class="rc-report-card-meta-item">
            <i class="fas fa-calendar-alt"></i>
            {{ formatDate(report.createdAt) }}
          </span>
          <template v-if="trashMode">
            <span class="rc-report-card-meta-item">
              <i class="fas fa-calendar-times"></i>
              删除时间{{ report.deletedAt ? formatDate(report.deletedAt) : '—' }}
            </span>
            <span class="rc-report-card-meta-item">
              <i class="fas fa-user-times"></i>
              删除人{{ report.deletedByUserId !== undefined && report.deletedByUserId !== null ? `用户 #${report.deletedByUserId}` : '—' }}
            </span>
          </template>
          <template v-if="report.type === 'comparison' || report.type === 'secondary_comparison'">
            <span class="rc-report-card-meta-item">
              <i class="fas fa-cubes"></i>
              {{ report.summary?.taskCount || 0 }} 个任务对比
            </span>
          </template>
          <template v-else-if="report.type === 'benchmark'">
            <span class="rc-report-card-meta-item">
              <i class="fas fa-trophy"></i>
              排行快照报告
            </span>
          </template>
          <template v-else>
            <span class="rc-report-card-meta-item">
              <i class="fas fa-list-check"></i>
              {{ report.summary?.totalCases || 0 }} 个测试用例
            </span>
            <span class="rc-report-card-meta-item">
              <i class="fas fa-check-circle"></i>
              {{ report.summary?.overallSuccessRate || report.summary?.passRate || 0 }}% 通过率
            </span>
          </template>
        </div>
      </div>
    </div>

    <!-- INT-969：加载失败独立错误态（区别于空态，可重试） -->
    <div v-if="!loading && error" class="rc-error-state">
      <i class="fas fa-exclamation-circle"></i>
      <p>{{ error }}</p>
      <button class="btn btn-secondary" @click="loadReports">
        <i class="fas fa-redo"></i> 重试
      </button>
    </div>

    <!-- 无数据提示 -->
    <div v-if="!loading && !error && allReports.length === 0" class="rc-no-data">
      <i class="fas fa-inbox"></i>
      <p>{{ trashMode ? '回收站是空的' : '暂无报告数据' }}</p>
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

    <!-- INT-483：发布 Benchmark 报告弹窗 -->
    <BenchmarkReportPublishModal
      v-if="benchmarkPublishVisible"
      :submitting="benchmarkSubmitting"
      @close="benchmarkPublishVisible = false"
      @confirm="handleBenchmarkPublish"
    />
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed, ref } from 'vue'
import { ReportStatus, PermissionPoint } from '@/domain/enums'
import { useReportCenter } from './reportCenter'
import { useAuthStore } from '../../store/authStore'
import { benchmarkReportsPort } from '../../composables/benchmark/benchmarkReportsPort'
import BenchmarkReportPublishModal from '../../components/benchmark-report/BenchmarkReportPublishModal.vue'
import BadgeFilter from '../../components/common/BadgeFilter.vue'
import FavoriteTrashBar from '../../components/common/FavoriteTrashBar.vue'
import Toast from '../../components/common/Toast.vue'
import VisibilityBadge from '../../components/common/visibility/VisibilityBadge.vue'
import { VISIBILITY_FILTER_OPTIONS, canEditResource } from '../../composables/visibility/useVisibility'
import AlgorithmFilter from '../../components/algorithm/AlgorithmFilter.vue'
import PaginationComponent from '../../components/common/data/PaginationComponent.vue'
import '../../assets/styles/reports/base.css'
import '../../assets/styles/reports/reports.css'
import '../../assets/styles/components/comparison-common.css'

const {
  allReports,
  totalItems,
  currentPage,
  pageSize,
  loading,
  error,
  selectedReports,
  filters,
  sort,
  algorithmOptions,
  toast,
  showToast,
  formatDate,
  getReportTypeLabel,
  getAlgorithmTypeLabel,
  getReportSummary,
  handleFilterChange,
  handleSortChange,
  clearDateRange,
  handlePrevPage,
  handleNextPage,
  handleGoToPage,
  handlePageSizeChange,
  isAllSelected,
  toggleSelectAll,
  toggleReportSelection,
  handleBatchDelete,
  handleBatchCancel,
  handleBatchCompare,
  handleBatchRestore,
  handleBatchPurge,
  viewReport,
  editReport,
  deleteReport,
  publishReport,
  favoriteOnly,
  trashMode,
  visibilityFilter,
  handleVisibilityFilterChange,
  toggleTrashMode,
  handleReportFavoriteFilterChange,
  loadReports,
  loadTabCounts,
  isFavorite,
  handleToggleFavorite,
  handleRestoreReport,
  handlePurgeReport,
  // G02 新增
  statCounts,
  isStatActive,
  handleStatBadgeClick,
  handleReportTypeFilterChange,
  goStatistics,
} = useReportCenter()

// ===== 统计徽章（数据源 tab-counts；快速筛选非页签）=====
const STAT_BADGES = [
  { key: 'all', label: '全部报告', icon: 'fas fa-layer-group', iconClass: 'rc-stat-icon--primary' },
  { key: 'published', label: '已发布', icon: 'fas fa-check-circle', iconClass: 'rc-stat-icon--success' },
  { key: 'draft', label: '草稿', icon: 'fas fa-edit', iconClass: 'rc-stat-icon--warning' },
  { key: 'comparison', label: '对比报告', icon: 'fas fa-exchange-alt', iconClass: 'rc-stat-icon--info' },
] as const

function getStatCount(key: (typeof STAT_BADGES)[number]['key']): number {
  return (statCounts as any)[key] ?? 0
}

// ===== 筛选选项（与 HistoryReports 对齐；类型=筛选条件，含 Benchmark）=====
const REPORT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'comparison', label: '对比报告' },
  { value: 'secondary_comparison', label: '二次对比报告' },
  { value: 'task', label: '任务报告' },
  { value: 'benchmark', label: 'Benchmark 报告' },
]

const REPORT_STATUS_OPTIONS = [
  { value: ReportStatus.DRAFT, label: '草稿' },
  { value: ReportStatus.PUBLISHED, label: '已发布' },
]

/** 时间范围选项（可变数组，适配 BadgeFilter 单选项契约；'all' 由「全部时间」徽章承担） */
const TIME_RANGE_OPTIONS: { value: string; label: string }[] = [
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
]

function handleReportStatusFilterChange(value: string | number) {
  filters.value.reportStatus = String(value) as any
  handleFilterChange()
}

function handleTimeRangeFilterChange(value: string | number) {
  filters.value.timeRange = String(value) as any
  handleFilterChange()
}

function handleAlgorithmFilterChange(value: string | number) {
  filters.value.algorithmType = String(value)
  handleFilterChange()
}

// ===== INT-483：发布 Benchmark 报告（POST /benchmarks/reports）=====
const { hasPermission: can } = useAuthStore()
const canPublishBenchmarkReport = computed(() => can(PermissionPoint.BENCHMARK_REPORT_PUBLISH))
const benchmarkPublishVisible = ref(false)
const benchmarkSubmitting = ref(false)

function openBenchmarkPublish() {
  benchmarkPublishVisible.value = true
}

async function handleBenchmarkPublish(payload: { name: string; description?: string; suite?: string; category?: string; source?: string }) {
  benchmarkSubmitting.value = true
  try {
    await benchmarkReportsPort.publish(payload)
    benchmarkPublishVisible.value = false
    showToast('success', 'Benchmark 报告发布成功')
    await Promise.all([loadReports(), loadTabCounts()])
  } catch (e: any) {
    showToast('error', '发布 Benchmark 报告失败: ' + (e?.message || '未知错误'))
  } finally {
    benchmarkSubmitting.value = false
  }
}
</script>

<style scoped>
.rc-report-center-view {
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
  color: var(--primary);
}

.page-description {
  margin: var(--spacing-xs) 0 0 0;
  color: var(--muted-foreground);
  font-size: var(--font-size-sm);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.benchmark-publish-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

/* ===== 统计徽章行 ===== */
.rc-stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.rc-stat-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--background);
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: left;
}

.rc-stat-badge:hover {
  border-color: var(--primary);
  box-shadow: var(--shadow-md);
}

.rc-stat-badge--active {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--accent);
}

.rc-stat-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
}

.rc-stat-icon--primary { background: var(--accent); color: var(--primary); }
.rc-stat-icon--success { background: var(--success-light); color: var(--success-dark); }
.rc-stat-icon--warning { background: var(--warning-light); color: var(--warning-dark); }
.rc-stat-icon--info { background: var(--secondary-light); color: var(--secondary); }

.rc-stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.rc-stat-label {
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
  white-space: nowrap;
}

.rc-stat-count {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--foreground);
  font-variant-numeric: tabular-nums;
}

/* ===== 筛选栏 ===== */
.rc-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
}

.rc-filter-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.rc-filter-item label {
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
  white-space: nowrap;
}

.rc-search-filter {
  flex: 1;
  min-width: 260px;
}

.rc-search-filter :deep(.search-input) {
  border: 2px solid var(--color-gray-300) !important;
  background-color: var(--background) !important;
  border-radius: var(--radius-lg) !important;
  padding: var(--spacing-sm) var(--spacing-md) !important;
  font-size: var(--font-size-md) !important;
  color: var(--foreground) !important;
  width: 100%;
}

.rc-search-filter :deep(.search-input:focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px var(--accent) !important;
}

.rc-custom-time-range {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.rc-custom-time-range .date-input {
  border: 2px solid var(--color-gray-300) !important;
  background-color: var(--background) !important;
  border-radius: var(--radius-md) !important;
  padding: var(--spacing-xs) var(--spacing-sm) !important;
  font-size: var(--font-size-sm) !important;
  color: var(--foreground) !important;
}

.rc-sort-options {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
}

.rc-sort-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  user-select: none;
}

.rc-sort-item.active {
  color: var(--primary);
  font-weight: var(--font-weight-semibold);
}

/* ===== 批量操作栏 ===== */
.rc-batch-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.rc-batch-select-all {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
}

.rc-select-all-label {
  font-size: var(--font-size-base);
  color: var(--foreground);
  user-select: none;
}

.rc-batch-action-buttons {
  display: flex;
  gap: var(--spacing-md);
}

/* ===== 加载 / 空态 ===== */
.rc-loading-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: var(--spacing-md);
  background: color-mix(in srgb, var(--primary) 5%, transparent);
  border-radius: var(--radius-lg);
  color: var(--muted-foreground);
  font-size: 14px;
}

.rc-loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid color-mix(in srgb, var(--primary) 30%, transparent);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: rc-spin 0.8s linear infinite;
}

@keyframes rc-spin {
  to { transform: rotate(360deg); }
}

.rc-no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--spacing-xxl);
  color: var(--text-tertiary);
}

.rc-no-data i {
  font-size: var(--font-size-xxxl);
  margin-bottom: var(--spacing-lg);
  color: var(--text-disabled);
}

.rc-no-data p {
  margin: 0;
  font-size: var(--font-size-md);
}

/* ===== 错误态（INT-969：区别于空态，可重试）===== */
.rc-error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--spacing-xxl);
  color: var(--color-red-600);
  gap: var(--spacing-sm);
}

.rc-error-state i {
  font-size: var(--font-size-xxxl);
  margin-bottom: var(--spacing-sm);
  color: var(--color-red-600);
}

.rc-error-state p {
  margin: 0;
  font-size: var(--font-size-md);
}

/* ===== 报告卡片 ===== */
.rc-report-card {
  border: var(--card-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
  background-color: var(--background);
  cursor: pointer;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.rc-report-card:hover {
  border-color: var(--primary);
}

.rc-card-selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--accent);
}

.rc-report-card .card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-sm);
  border-bottom: none;
  background: transparent;
}

.rc-report-checkbox-wrapper {
  display: flex;
  align-items: center;
  margin-right: var(--spacing-md);
}

.rc-report-card-title-wrapper {
  flex: 1;
  min-width: 0;
}

.rc-report-card-title {
  margin: 0 0 var(--spacing-xs) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--foreground);
}

.rc-report-card-meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  align-items: center;
}

.rc-report-card-type,
.rc-report-card-status,
.rc-report-card-algorithm-type,
.rc-report-card-test-type {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.rc-report-card-type {
  background-color: var(--info-light);
  color: var(--info);
}

.rc-status-published {
  background-color: var(--success-light);
  color: var(--success-dark);
}

.rc-status-draft {
  background-color: var(--warning-light);
  color: var(--warning);
}

.rc-report-card-algorithm-type {
  background-color: var(--color-sky-50);
  color: var(--color-sky-600);
}

.rc-report-card-test-type {
  background-color: var(--accent);
  color: var(--primary);
}

.rc-report-card-description {
  color: var(--muted-foreground);
  font-size: var(--font-size-sm);
  margin: 0 0 var(--spacing-sm) 0;
}

.rc-report-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.rc-report-card-meta-item {
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.rc-report-card-meta-item i {
  color: var(--primary);
}

.task-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--primary);
}
</style>
