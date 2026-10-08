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
        
        <div class="filter-item">
          <label for="report-status-filter">报告状态：</label>
          <select class="filter-select" 
                  id="report-status-filter"
                  v-model="filters.reportStatus"
                  @change="handleFilterChange">
            <option value="all">全部状态</option>
            <option :value="ReportStatus.DRAFT">草稿</option>
            <option :value="ReportStatus.PUBLISHED">已发布</option>
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
              {{ option.label }}
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
    
    <!-- 报告列表：按当前视图 Tab 分组展示（全部=已发布+草稿分区；其余=单组统一列表） -->
    <div
      v-for="section in reportSections"
      :key="section.key"
      class="reports-section"
      :class="{ 'draft-section': section.draft }"
    >
      <div class="section-header">
        <h3 class="section-title">
          <i :class="section.icon" :style="{ color: section.iconColor }"></i>
          {{ section.title }} ({{ section.reports.length }})
        </h3>
      </div>

      <div v-for="report in section.reports" :key="report.id" class="card" :class="{ 'card-selected': selectedReports.has(report.id) }" @click="toggleReportSelection(report.id, $event)">
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
              <span class="report-card-status" :class="report.status === ReportStatus.DRAFT ? 'draft' : 'published'">
                {{ report.status === ReportStatus.DRAFT ? '草稿' : '已发布' }}
              </span>
              <span v-if="report.algorithmType" class="report-card-algorithm-type">{{ getAlgorithmTypeLabel(report.algorithmType) }}</span>
              <span v-if="report.taskName" class="report-card-test-type">{{ report.taskName }}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn btn-primary" @click.stop="viewReport(report.id, report.type)">
              <i class="fas fa-eye"></i> 查看
            </button>
            <button class="btn btn-secondary" @click.stop="editReport(report.id)">
              <i class="fas fa-edit"></i> 编辑
            </button>
            <button class="btn btn-danger" @click.stop="deleteReport(report.id)">
              <i class="fas fa-trash"></i> 删除
            </button>
            <button v-if="report.status === ReportStatus.DRAFT" class="btn btn-success" @click.stop="publishReport(report.id)">
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
            <template v-if="report.type === 'comparison' || report.type === 'secondaryComparison'">
              <span class="report-card-meta-item">
                <i class="fas fa-cubes"></i>
                {{ report.summary?.taskCount || 0 }} 个任务对比
              </span>
            </template>
            <template v-else>
              <span class="report-card-meta-item">
                <i class="fas fa-list-check"></i>
                {{ report.summary?.totalCases || 0 }} 个测试用例
              </span>
              <span class="report-card-meta-item">
                <i class="fas fa-check-circle"></i>
                {{ report.summary?.overallSuccessRate || report.summary?.passRate || 0 }}% 通过率
              </span>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 无数据提示：按当前视图 Tab 判断 -->
    <div v-if="reportSections.length === 0" class="no-data">
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
import { ReportStatus } from '@/domain/enums';
import type { Report } from '../../domain';
import { useHistoryReports, REPORT_TABS } from './historyReports';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';

const {
  allReports,
  totalItems,
  currentPage,
  pageSize,
  loading,
  selectedReports,
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
  activeTab,
  reportTabOptions,
  visibleReports,
  getTabCount,
  handleTabChange,
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
  publishReport
} = useHistoryReports();

/** 当前激活 Tab 的元信息（用于统一列表的标题/图标） */
const activeTabMeta = computed(
  () => reportTabOptions.find(tab => tab.value === activeTab.value) || reportTabOptions[0]
);

/** 报告列表分组：按当前视图 Tab 决定展示的分组（全部=已发布+草稿分区；其余=单组统一列表） */
interface ReportViewSection {
  key: string;
  draft: boolean;
  title: string;
  icon: string;
  iconColor: string;
  reports: Report[];
}

const reportSections = computed<ReportViewSection[]>(() => {
  if (activeTab.value === REPORT_TABS.ALL) {
    return [
      { key: 'published', draft: false, title: '已发布报告', icon: 'fas fa-check-circle', iconColor: 'var(--success-color)', reports: publishedReports.value },
      { key: 'draft', draft: true, title: '草稿报告', icon: 'fas fa-edit', iconColor: 'var(--warning-color)', reports: draftReports.value },
    ].filter(section => section.reports.length > 0);
  }
  return [{
    key: `single-${activeTab.value}`,
    draft: false,
    title: activeTabMeta.value.label,
    icon: activeTabMeta.value.icon,
    iconColor: 'var(--primary-color)',
    reports: visibleReports.value,
  }].filter(section => section.reports.length > 0);
});

// 报告类型选项（原下拉框硬编码迁移为常量）
const REPORT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'comparison', label: '对比报告' },
  { value: 'secondaryComparison', label: '二次对比报告' },
  { value: 'task', label: '任务报告' },
];

function handleReportTypeFilterChange(value: string | number) {
  filters.value.reportType = String(value) as any;
  handleFilterChange();
}
</script>

<style scoped>@import './HistoryReports.css';



.no-data{
display: flex;
flex-direction: column;
align-items: center;
justify-content: center;
text-align: center;
padding: var(--spacing-xxl);
color: var(--text-tertiary);
}

.no-data i{
font-size: var(--font-size-xxxl);
margin-bottom: var(--spacing-lg);
color: var(--text-disabled);
}

.no-data p{
    margin: 0;
    font-size: var(--font-size-md);
}

.report-card-type,
.report-card-status,


.report-card-status{
    background-color: var(--info-light);
    color: var(--info-color);
}














/* report-card-title-wrapper - 自全局样式就近迁移 */



/* report-card-title - 自全局样式就近迁移 */



/* report-card-meta-tags - 自全局样式就近迁移 */



/* report-card-type - 自全局样式就近迁移 */



/* report-card-test-type - 自全局样式就近迁移 */





/* report-checkbox-wrapper - 自全局样式就近迁移 */



/* report-card-description - 自全局样式就近迁移 */



/* report-card-meta - 自全局样式就近迁移 */



</style>
