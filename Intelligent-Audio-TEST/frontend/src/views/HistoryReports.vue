<template>
  <div class="history-reports-view">
    <!-- Toast 提示：Teleport 到全局固定元素容器，避免被 .main-content 的 transform 截获 fixed 包含块导致随页面滚动 -->
    <teleport to="#global-fixed-elements">
      <div v-if="toast" class="toast-container" :class="`toast-${toast.type}`">
        <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : toast.type === 'warning' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle'"></i>
        <span>{{ toast.message }}</span>
      </div>
    </teleport>
    
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-history"></i>
          历史报告
        </h2>
        <p class="page-description">查看和管理所有历史报告</p>
      </div>
    </div>

    <!-- 视图 Tab 栏 -->
    <div class="report-tabs" role="tablist">
      <button
        v-for="tab in reportTabOptions"
        :key="tab.value"
        class="report-tab"
        :class="{ active: activeTab === tab.value }"
        role="tab"
        :aria-selected="activeTab === tab.value"
        @click="handleTabChange(tab.value)"
      >
        <i :class="tab.icon"></i>
        <span>{{ tab.label }}</span>
        <span class="report-tab-count">{{ getTabCount(tab.value) }}</span>
      </button>
    </div>
    
    <!-- 筛选和排序栏 -->
    <section class="filter-sort-section">
      <div class="filter-row">
        <div class="filter-item search-filter">
          <label>搜索报告：</label>
          <input type="text" 
                 class="search-input" 
                 placeholder="搜索报告名称、创建时间..." 
                 v-model="filters.search"
                 @input="handleFilterChange">
        </div>
        
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
      
      <div class="filter-row">
        <!-- 自定义时间范围 -->
        <div class="filter-item custom-time-range" v-if="filters.timeRange === 'custom'">
          <div>
            <label for="start-date">开始:</label>
            <input type="date" 
                   id="report-start-date" 
                   class="date-input"
                   v-model="filters.startDate"
                   @change="handleFilterChange">
          </div>
          <span>至</span>
          <div>
            <label for="end-date">结束:</label>
            <input type="date" 
                   id="report-end-date" 
                   class="date-input"
                   v-model="filters.endDate"
                   @change="handleFilterChange">
          </div>
          <button class="btn btn-secondary" @click="clearDateRange">
            <i class="fas fa-times"></i> 清除
          </button>
        </div>
        
        <div class="sort-options">
          <span>排序：</span>
          <div class="sort-item" 
               :class="{ 'active': sort.sortBy === 'createdAt' }"
               @click="handleSortChange('createdAt')">
            创建时间 
            <i class="fas fa-sort-down" v-if="sort.sortBy === 'createdAt' && sort.order === 'desc'"></i>
            <i class="fas fa-sort-up" v-else-if="sort.sortBy === 'createdAt' && sort.order === 'asc'"></i>
            <i class="fas fa-sort" v-else></i>
          </div>
          <div class="sort-item" 
               :class="{ 'active': sort.sortBy === 'name' }"
               @click="handleSortChange('name')">
            报告名称 
            <i class="fas fa-sort-down" v-if="sort.sortBy === 'name' && sort.order === 'desc'"></i>
            <i class="fas fa-sort-up" v-else-if="sort.sortBy === 'name' && sort.order === 'asc'"></i>
            <i class="fas fa-sort" v-else></i>
          </div>
        </div>
      </div>
      
      <!-- 算法筛选（徽章单选） -->
      <div class="filter-row">
        <AlgorithmFilter
          :options="algorithmOptions"
          :model-value="filters.algorithmType"
          title="算法筛选"
          @update:model-value="handleAlgorithmFilterChange"
        />
      </div>
    </section>
    
    <!-- 批量操作栏 -->
    <div class="batch-actions" v-if="allReports.length > 0">
      <div class="batch-select-all">
        <input type="checkbox" 
               id="select-all-reports" 
               class="task-checkbox"
               v-model="isAllSelected"
               @change="toggleSelectAll">
        <label for="select-all-reports"></label>
        <span class="select-all-label">全选</span>
      </div>
      <div v-if="selectedReports.size > 0" class="batch-action-buttons">
        <button class="btn btn-success" @click="handleBatchCompare">
          <i class="fas fa-exchange-alt"></i> 批量对比
        </button>
        <button class="btn btn-danger" @click="handleBatchDelete">
          <i class="fas fa-trash"></i> 批量删除 ({{ selectedReports.size }})
        </button>
        <button class="btn btn-secondary" @click="handleBatchCancel">
          <i class="fas fa-times"></i> 取消选择
        </button>
      </div>
    </div>
    
    <!-- 全部报告视图：按发布状态分组展示 -->
    <template v-if="activeTab === REPORT_TABS.ALL">
      <!-- 已发布报告区域 -->
      <div class="reports-section" v-if="publishedReports.length > 0">
        <div class="section-header">
          <h3 class="section-title">
            <i class="fas fa-check-circle" style="color: var(--success-color);"></i>
            已发布报告 ({{ publishedReports.length }})
          </h3>
        </div>

        <div id="published-reports-list">
          <ReportCard
            v-for="report in publishedReports"
            :key="report.id"
            :report="report"
            :selected="selectedReports.has(report.id)"
            :summary="getReportSummary(report)"
            :algorithm-type-label="getAlgorithmTypeLabel(report.algorithmType)"
            @toggle-select="toggleReportSelection"
            @view="viewReport"
            @edit="editReport"
            @delete="deleteReport"
            @publish="publishReport"
          />
        </div>
      </div>

      <!-- 草稿报告区域 -->
      <div class="reports-section draft-section" v-if="draftReports.length > 0">
        <div class="section-header">
          <h3 class="section-title">
            <i class="fas fa-edit" style="color: var(--warning-color);"></i>
            草稿报告 ({{ draftReports.length }})
          </h3>
        </div>

        <div id="draft-reports-list">
          <ReportCard
            v-for="report in draftReports"
            :key="report.id"
            :report="report"
            :selected="selectedReports.has(report.id)"
            :summary="getReportSummary(report)"
            :algorithm-type-label="getAlgorithmTypeLabel(report.algorithmType)"
            @toggle-select="toggleReportSelection"
            @view="viewReport"
            @edit="editReport"
            @delete="deleteReport"
            @publish="publishReport"
          />
        </div>
      </div>
    </template>

    <!-- 单个视图 Tab（草稿/发布/对比）：统一列表 -->
    <template v-else>
      <div class="reports-section" v-if="visibleReports.length > 0">
        <div class="section-header">
          <h3 class="section-title">
            <i :class="activeTabMeta.icon" style="color: var(--primary-color);"></i>
            {{ activeTabMeta.label }} ({{ visibleReports.length }})
          </h3>
        </div>

        <div id="tab-reports-list">
          <ReportCard
            v-for="report in visibleReports"
            :key="report.id"
            :report="report"
            :selected="selectedReports.has(report.id)"
            :summary="getReportSummary(report)"
            :algorithm-type-label="getAlgorithmTypeLabel(report.algorithmType)"
            @toggle-select="toggleReportSelection"
            @view="viewReport"
            @edit="editReport"
            @delete="deleteReport"
            @publish="publishReport"
          />
        </div>
      </div>
    </template>
    
    <!-- 无数据提示：按当前 Tab 判断当前视图是否为空 -->
    <div
      v-if="activeTab === REPORT_TABS.ALL ? allReports.length === 0 : visibleReports.length === 0"
      class="no-data"
    >
      <i class="fas fa-inbox"></i>
      <p>{{ activeTab === REPORT_TABS.ALL ? '暂无报告数据' : `暂无${activeTabMeta.label}数据` }}</p>
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
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useHistoryReports } from './HistoryReportsLogic/historyReports';
import { REPORT_TABS } from '../shared/constants/reportConstants';

import AlgorithmFilter from '../components/algorithm/AlgorithmFilter.vue';
import BadgeFilter from '../components/common/BadgeFilter.vue';
import PaginationComponent from '../components/common/PaginationComponent.vue';
import ReportCard from '../components/report/ReportCard.vue';

const router = useRouter();

const {
  allReports,
  totalItems,
  currentPage,
  pageSize,
  selectedReports,
  filters,
  sort,
  algorithmOptions,
  toast,
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
  activeTab,
  reportTabOptions,
  publishedReports,
  draftReports,
  visibleReports,
  getTabCount,
  handleTabChange,
  toggleSelectAll,
  toggleReportSelection,
  handleBatchDelete,
  handleBatchCancel,
  handleBatchCompare,
  viewReport,
  editReport,
  deleteReport,
  publishReport
} = useHistoryReports();

const activeTabMeta = computed(
  () => reportTabOptions.find(tab => tab.value === activeTab.value) || reportTabOptions[0]
);

/** 算法徽章筛选变更（单选） */
function handleAlgorithmFilterChange(value: string) {
  filters.value.algorithmType = value;
  handleFilterChange();
}

/** 报告类型 / 状态 / 时间范围选项（原下拉框硬编码迁移为常量） */
const REPORT_TYPE_OPTIONS = [
  { value: 'comparison', label: '对比报告' },
  { value: 'secondary_comparison', label: '二次对比报告' },
  { value: 'task', label: '任务报告' },
];

const REPORT_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '已发布' },
];

const TIME_RANGE_OPTIONS = [
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
];

function handleReportTypeFilterChange(value: string | number) {
  filters.value.reportType = String(value) as any;
  handleFilterChange();
}

function handleReportStatusFilterChange(value: string | number) {
  filters.value.reportStatus = String(value) as any;
  handleFilterChange();
}

function handleTimeRangeFilterChange(value: string | number) {
  filters.value.timeRange = String(value) as any;
  handleFilterChange();
}
</script>

<style scoped>
/* 只导入主样式文件，所有组件样式已包含在main.css中 */
@import '../assets/styles/main.css';

/* 搜索框样式 - 确保外框为明显的灰色 */
.filter-sort-section :deep(.search-input) {
  border: 2px solid #D1D5DB !important;
  background-color: white !important;
  border-radius: var(--border-radius-lg) !important;
  padding: var(--spacing-sm) var(--spacing-md) !important;
  font-size: var(--font-size-md) !important;
}

/* 搜索框聚焦状态样式 */
.filter-sort-section :deep(.search-input:focus) {
  border-color: var(--primary-color) !important;
  box-shadow: 0 0 0 3px var(--primary-light) !important;
  background-color: white !important;
}

/* 视图 Tab 栏样式 */
.report-tabs {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-sm);
  background: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  border: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.report-tab {
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

.report-tab:hover {
  background: var(--background-primary);
  color: var(--primary-color);
}

.report-tab.active {
  background: var(--primary-color);
  color: #fff;
  border-color: var(--primary-color);
  box-shadow: var(--shadow-sm);
}

.report-tab-count {
  padding: 1px 8px;
  border-radius: var(--border-radius-full);
  background: rgba(0, 0, 0, 0.08);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
}

.report-tab.active .report-tab-count {
  background: rgba(255, 255, 255, 0.25);
  color: #fff;
}

/* 批量操作栏样式 */
.batch-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.batch-select-all {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
}

.select-all-label {
  font-size: var(--font-size-base);
  color: var(--text-primary);
  user-select: none;
}

.batch-action-buttons {
  display: flex;
  gap: var(--spacing-md);
}

/* 报告区域样式 */
.reports-section {
  margin-bottom: 32px;
}

.reports-section.draft-section {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 2px dashed #e2e8f0;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
}

.section-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title i {
  font-size: 1rem;
}

/* 状态标签样式 */
.report-card-status.published {
  background-color: var(--success-light, #f0fdf4);
  color: var(--success-color, #16a34a);
  border: 1px solid var(--success-color, #16a34a);
}

.report-card-status.draft {
  background-color: var(--warning-light, #fffbeb);
  color: var(--warning-color, #d97706);
  border: 1px solid var(--warning-color, #d97706);
}

.report-card-algorithm-type {
  background-color: #f0f9ff;
  color: #0284c7;
  border: 1px solid #0284c7;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 10000;
  animation: slideIn 0.3s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.toast-container i {
  font-size: 1.2rem;
}

.toast-success {
  background-color: #f0fdf4;
  color: #16a34a;
  border: 1px solid #16a34a;
}

.toast-error {
  background-color: #fef2f2;
  color: #dc2626;
  border: 1px solid #dc2626;
}

.toast-warning {
  background-color: #fffbeb;
  color: #d97706;
  border: 1px solid #d97706;
}

.toast-info {
  background-color: #eff6ff;
  color: #2563eb;
  border: 1px solid #2563eb;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>
