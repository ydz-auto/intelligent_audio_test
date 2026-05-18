<template>
  <div class="history-reports-view">
    <!-- Toast 提示 -->
    <div v-if="toast" class="toast-container" :class="`toast-${toast.type}`">
      <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : toast.type === 'warning' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle'"></i>
      <span>{{ toast.message }}</span>
    </div>
    
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-history"></i>
          历史报告
        </h2>
        <p class="page-description">查看和管理已保存的对比报告</p>
      </div>
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
        
        <div class="filter-item">
          <label for="report-type-filter">报告类型：</label>
          <select class="filter-select" 
                  id="report-type-filter"
                  v-model="filters.reportType"
                  @change="handleFilterChange">
            <option value="all">全部类型</option>
            <option value="comparison">对比报告</option>
            <option value="secondaryComparison">二次对比报告</option>
            <option value="task">任务报告</option>
          </select>
        </div>
        
        <div class="filter-item">
          <label for="report-status-filter">报告状态：</label>
          <select class="filter-select" 
                  id="report-status-filter"
                  v-model="filters.reportStatus"
                  @change="handleFilterChange">
            <option value="all">全部状态</option>
            <option value="draft">草稿</option>
            <option value="published">发布</option>
          </select>
        </div>
        
        <div class="filter-item">
          <label for="time-filter">时间范围：</label>
          <select class="filter-select" 
                  id="time-filter"
                  v-model="filters.timeRange"
                  @change="handleFilterChange">
            <option value="all">全部时间</option>
            <option value="today">今日</option>
            <option value="yesterday">昨日</option>
            <option value="week">近7天</option>
            <option value="month">近30天</option>
            <option value="custom">自定义</option>
          </select>
        </div>
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
        
        <div class="filter-item">
          <label for="algorithm-type-filter">算法类型：</label>
          <select class="filter-select" 
                  id="algorithm-type-filter"
                  v-model="filters.algorithmType"
                  @change="handleFilterChange">
            <option value="all">全部类型</option>
            <option v-for="option in algorithmOptions" :key="option.value" :value="option.value">
              {{ option.name }}
            </option>
          </select>
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
    </section>
    
    <!-- 历史报告列表表格视图 - 暂时注释，优先显示卡片视图 -->
    <!-- <ComparisonTableComponent 
      title="历史报告列表"
      :columns="reportColumns"
      :data="sortedReports"
      :show-pagination="false"
      @export="handleBatchExport"
    /> -->
    
    <!-- 报告列表 -->
    <section class="reports-container" v-if="!showComparisonReport">
            <!-- 批量操作栏（仅在有报告时显示） -->
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
      
      <!-- 已发布报告区域 -->
      <div class="reports-section" v-if="publishedReports.length > 0">
        <div class="section-header">
          <h3 class="section-title">
            <i class="fas fa-check-circle" style="color: var(--success-color);"></i>
            已发布报告 ({{ publishedReports.length }})
          </h3>
        </div>
        
        <div id="published-reports-list">
          <div v-for="report in publishedReports" :key="report.id" class="card" :class="{ 'card-selected': selectedReports.has(report.id) }" @click="toggleReportSelection(report.id, $event)">
            <div class="card-header">
              <div class="report-checkbox-wrapper">
                <input type="checkbox" 
                       class="task-checkbox" 
                       :id="`report-${report.id}`" 
                       :checked="selectedReports.has(report.id)"
                       @change="selectedReports.has(report.id) ? selectedReports.delete(report.id) : selectedReports.add(report.id)"
                       @click.stop>
                <label :for="`report-${report.id}`"></label>
              </div>
              <div class="report-card-title-wrapper">
                <h3 class="report-card-title">{{ report.name }}</h3>
                <div class="report-card-meta-tags">
                  <span class="report-card-type">{{ getReportTypeLabel(report.type) }}</span>
                  <span class="report-card-status published">发布</span>
                  <span v-if="report.algorithmType" class="report-card-algorithm-type">{{ getAlgorithmTypeLabel(report.algorithmType) }}</span>
                  <span v-if="report.taskName" class="report-card-test-type">{{ report.taskName }}</span>
                </div>
              </div>
              <div class="card-actions">
                <button class="btn btn-primary" @click="viewReport(report.id)">
                  <i class="fas fa-eye"></i> 查看
                </button>
                <button class="btn btn-secondary" @click="editReport(report.id)">
                  <i class="fas fa-edit"></i> 编辑
                </button>
                <button class="btn btn-danger" @click="deleteReport(report.id)">
                  <i class="fas fa-trash"></i> 删除
                </button>
              </div>
            </div>
            <div class="card-body">
              <p class="report-card-description">{{ report.description || getReportSummary(report) }}</p>
              <div class="report-card-meta">
                <span class="report-card-meta-item">
                  <i class="fas fa-calendar-alt"></i>
                  {{ formatDate(report.createdAt) }}
                </span>
                <template v-if="report.type === 'comparison'">
                  <span class="report-card-meta-item">
                    <i class="fas fa-cubes"></i>
                    {{ report.summary?.taskCount || 0 }} 个任务对比
                  </span>
                </template>
                <template v-else>
                  <span class="report-card-meta-item">
                    <i class="fas fa-list-check"></i>
                    {{ report.summary?.totalCases || report.summary?.totalTests || report.summary?.total_cases || 0 }} 个测试用例
                  </span>
                  <span class="report-card-meta-item">
                    <i class="fas fa-check-circle"></i>
                    {{ report.summary?.overallSuccessRate || report.summary?.passRate || report.summary?.overall_success_rate || 0 }}% 通过率
                  </span>
                </template>
              </div>
            </div>
          </div>
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
          <div v-for="report in draftReports" :key="report.id" class="card" :class="{ 'card-selected': selectedReports.has(report.id) }" @click="toggleReportSelection(report.id, $event)">
            <div class="card-header">
              <div class="report-checkbox-wrapper">
                <input type="checkbox" 
                       class="task-checkbox" 
                       :id="`report-${report.id}`" 
                       :checked="selectedReports.has(report.id)"
                       @change="selectedReports.has(report.id) ? selectedReports.delete(report.id) : selectedReports.add(report.id)"
                       @click.stop>
                <label :for="`report-${report.id}`"></label>
              </div>
              <div class="report-card-title-wrapper">
                <h3 class="report-card-title">{{ report.name }}</h3>
                <div class="report-card-meta-tags">
                  <span class="report-card-type">{{ getReportTypeLabel(report.type) }}</span>
                  <span class="report-card-status draft">草稿</span>
                  <span v-if="report.algorithmType" class="report-card-algorithm-type">{{ getAlgorithmTypeLabel(report.algorithmType) }}</span>
                  <span v-if="report.taskName" class="report-card-test-type">{{ report.taskName }}</span>
                </div>
              </div>
              <div class="card-actions">
                <button class="btn btn-primary" @click="viewReport(report.id)">
                  <i class="fas fa-eye"></i> 查看
                </button>
                <button class="btn btn-secondary" @click="editReport(report.id)">
                  <i class="fas fa-edit"></i> 编辑
                </button>
                <button class="btn btn-danger" @click="deleteReport(report.id)">
                  <i class="fas fa-trash"></i> 删除
                </button>
                <button class="btn btn-success" @click="publishReport(report.id)">
                  <i class="fas fa-paper-plane"></i> 发布
                </button>
              </div>
            </div>
            <div class="card-body">
              <p class="report-card-description">{{ report.description || getReportSummary(report) }}</p>
              <div class="report-card-meta">
                <span class="report-card-meta-item">
                  <i class="fas fa-calendar-alt"></i>
                  {{ formatDate(report.createdAt) }}
                </span>
                <template v-if="report.type === 'comparison'">
                  <span class="report-card-meta-item">
                    <i class="fas fa-cubes"></i>
                    {{ report.summary?.taskCount || 0 }} 个任务对比
                  </span>
                </template>
                <template v-else>
                  <span class="report-card-meta-item">
                    <i class="fas fa-list-check"></i>
                    {{ report.summary?.totalCases || report.summary?.totalTests || report.summary?.total_cases || 0 }} 个测试用例
                  </span>
                  <span class="report-card-meta-item">
                    <i class="fas fa-check-circle"></i>
                    {{ report.summary?.overallSuccessRate || report.summary?.passRate || report.summary?.overall_success_rate || 0 }}% 通过率
                  </span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 无数据提示 -->
      <div v-if="allReports.length === 0" class="no-data">
        <i class="fas fa-inbox"></i>
        <p>暂无报告数据</p>
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
      
    </section>
    
    <!-- 历史报告对比报告区域 -->
    <section class="comparison-report-container" v-if="showComparisonReport">
      <TaskReportPanel 
        :report="reportService.comparisonReport.value"
        :is-editing-report="isEditingReport"
        :is-editing-conclusion="isEditingConclusion"
        :analysis-content="reportService.comparisonReport.value?.conclusion || ''"
        :tables="[]"
        @toggle-edit="toggleEditReport"
        @save-report="saveComparisonReport"
        @cancel-edit="cancelEditReport"
        @toggle-conclusion-edit="toggleEditConclusion"
        @save-conclusion="saveConclusion"
        @cancel-conclusion="cancelEditConclusion"
      />
    </section>
    <div class="floating-actions-bar" v-if="showComparisonReport">
      <button class="btn btn-primary" @click="saveComparisonReport">
        <i class="fas fa-save"></i> 保存
      </button>
      <button class="btn btn-success" @click="publishComparisonReport">
        <i class="fas fa-paper-plane"></i> 发布
      </button>
      <button class="btn btn-secondary" @click="closeComparisonReport">
        <i class="fas fa-times"></i> 关闭
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useHistoryReports } from './HistoryReportsLogic/historyReports';
import { sanitizeConclusion } from '../utils/sanitize';

import TaskReportPanel from '../components/report/TaskReportPanel.vue'
import ComparisonTableComponent from '../components/report/ComparisonTableComponent.vue'
import ChartComponent from '../components/report/ChartComponent.vue'
import CaseCategoryComparisonComponent from '../components/report/CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from '../components/report/CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from '../components/report/SpecificCaseComparisonComponent.vue'
import OverviewCardComponent from '../components/report/OverviewCardComponent.vue'
import PaginationComponent from '../components/common/PaginationComponent.vue'

const {
  reportService,
  allReports,
  totalItems,
  currentPage,
  pageSize,
  loading,
  selectedReports,
  showComparisonReport,
  isEditingReport,
  isEditingConclusion,
  filters,
  sort,
  algorithmOptions,
  toast,
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
  totalPages,
  isAllSelected,
  publishedReports,
  draftReports,
  toggleSelectAll,
  toggleReportSelection,
  handleBatchDelete,
  handleBatchCancel,
  handleBatchCompare,
  viewReport,
  editReport,
  deleteReport,
  publishReport,
  closeComparisonReport,
  saveComparisonReport,
  publishComparisonReport,
  exportComparisonReport,
  toggleEditReport,
  cancelEditReport,
  toggleEditConclusion,
  cancelEditConclusion,
  saveConclusion
} = useHistoryReports();

const reportConclusion = computed({
  get: () => reportService.comparisonReport.value?.conclusion || '',
  set: (val: string) => {
    if (reportService.comparisonReport.value) {
      reportService.comparisonReport.value.conclusion = val;
    }
  }
});

const sanitizedConclusion = computed(() => {
  return sanitizeConclusion(reportConclusion.value);
});
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

/* 下拉选择框样式 - 确保外框为明显的灰色 */
.filter-sort-section :deep(.filter-select) {
  border: 2px solid #D1D5DB !important;
  background-color: white !important;
  border-radius: var(--border-radius-md) !important;
  padding: var(--spacing-sm) var(--spacing-md) !important;
  font-size: var(--font-size-md) !important;
}

/* 下拉选择框聚焦状态样式 */
.filter-sort-section :deep(.filter-select:focus) {
  border-color: var(--primary-color) !important;
  box-shadow: 0 0 0 3px var(--primary-light) !important;
  background-color: white !important;
}

/* 全选按钮样式 */
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

.comparison-selectors {
  margin-bottom: 24px;
}

.selector-title {
  margin-bottom: 16px;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.selector-content {
  background: #ffffff;
  padding: 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

#unified-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.device-select-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  width: 130px;
  height: 150px;
  position: relative;
  overflow: hidden;
}

.device-select-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border-color: #cbd5e1;
}

.device-select-item.selected {
  border-color: #FF6A00;
  background-color: #fffaf0;
}

.device-select-item.api-item.selected {
  border-color: #1677FF;
  background-color: #f0f7ff;
}

.device-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: #f8fafc;
  transition: all 0.3s ease;
}

.device-select-item.selected .device-icon-wrapper {
  background: rgba(255, 106, 0, 0.1);
}

.device-select-item.api-item.selected .device-icon-wrapper {
  background: rgba(22, 119, 255, 0.1);
}

.device-icon-wrapper i {
  font-size: 24px;
  color: #64748b;
}

.device-select-item.selected .device-icon-wrapper i {
  color: #FF6A00;
}

.device-select-item.api-item.selected .device-icon-wrapper i {
  color: #1677FF;
}

.device-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.device-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #1e293b;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.device-type-tag {
  font-size: 0.75rem;
  color: #64748b;
  padding: 2px 8px;
  background: #f1f5f9;
  border-radius: 10px;
}

.selection-indicator {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transform: scale(0.5);
  transition: all 0.3s ease;
}

.device-select-item.selected .selection-indicator {
  opacity: 1;
  transform: scale(1);
}

.selection-indicator i {
  font-size: 18px;
  color: #FF6A00;
}

.device-select-item.api-item.selected .selection-indicator i {
  color: #1677FF;
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

.report-detail-algorithm-type {
  background-color: #fff7ed;
  color: #ea580c;
  border: 1px solid #ea580c;
  padding: 4px 12px;
  border-radius: 16px;
  font-size: 0.8rem;
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

.floating-actions-bar {
  position: fixed !important;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
  z-index: 14000 !important;
  padding: 12px 20px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.floating-actions-bar .btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
}

.floating-actions-bar .btn-primary {
  background: #1677FF;
  color: white;
}

.floating-actions-bar .btn-primary:hover {
  background: #0958D9;
}

.floating-actions-bar .btn-success {
  background: #52C41A;
  color: white;
}

.floating-actions-bar .btn-success:hover {
  background: #389E0D;
}

.floating-actions-bar .btn-secondary {
  background: #f1f5f9;
  color: #64748b;
}

.floating-actions-bar .btn-secondary:hover {
  background: #e2e8f0;
}
</style>
