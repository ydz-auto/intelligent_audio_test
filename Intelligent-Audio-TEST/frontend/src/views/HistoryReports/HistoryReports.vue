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
      <!-- INT-483：发布 Benchmark 报告入口（权限 benchmark:report:publish 显隐） -->
      <button v-if="canPublishBenchmarkReport" class="btn btn-primary benchmark-publish-btn" @click="openBenchmarkPublish">
        <i class="fas fa-trophy"></i> 发布 Benchmark 报告
      </button>
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

        <AlgorithmFilter
          :options="algorithmOptions"
          :model-value="filters.algorithmType"
          title="算法筛选"
          @update:model-value="handleAlgorithmFilterChange"
        />

        <!-- INT-423/467：可见性筛选（全部/共享/私有；服务端 ?visibility= 行级过滤） -->
        <BadgeFilter
          :options="VISIBILITY_FILTER_OPTIONS"
          :model-value="visibilityFilter || 'all'"
          all-label="全部"
          title="可见性"
          @update:model-value="handleVisibilityFilterChange"
        />

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
    
    <!-- INT-141：收藏 / 回收站工具栏（INT-215：收敛至 common 组件，三视图统一口径） -->
    <FavoriteTrashBar
      :favorite-only="favoriteOnly"
      :trash-mode="trashMode"
      :favorite-disabled="trashMode"
      @update:favorite-only="handleReportFavoriteFilterChange"
      @update:trash-mode="toggleTrashMode"
    />

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
        <!-- INT-215/S4：回收站态批量栏适配——对比/删除对已删报告为 no-op，屏蔽之；
             补批量恢复/批量彻底删除（对齐任务侧已有能力） -->
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
    
    <!-- INT-290 加载指示（对齐 A/B 域 loading bar 方案；重载期间保留旧列表不闪空） -->
    <div v-if="loading" class="history-reports-loading-bar">
      <span class="loading-spinner"></span>
      正在加载报告...
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
              <!-- INT-423/467：可见性徽标（私有带锁图标） -->
              <VisibilityBadge :visibility="report.visibility" />
              <span v-if="report.algorithmType" class="report-card-algorithm-type">{{ getAlgorithmTypeLabel(report.algorithmType) }}</span>
              <span v-if="report.taskName" class="report-card-test-type">{{ report.taskName }}</span>
            </div>
          </div>
          <div class="card-actions">
            <!-- INT-141：回收站模式（恢复/彻底删除） -->
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
              <!-- INT-536：私有报告非 owner（含 admin 豁免见 canEditResource）隐藏编辑/删除入口 -->
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
          <p class="report-card-description">{{ report.description || getReportSummary(report) }}</p>
          <div class="report-card-meta">
            <span class="report-card-meta-item">
              <i class="fas fa-calendar-alt"></i>
              {{ formatDate(report.createdAt) }}
            </span>
            <!-- INT-215：回收站条目展示删除人/删除时间（后端字段补齐前 NULL 显示「—」） -->
            <template v-if="trashMode">
              <span class="report-card-meta-item">
                <i class="fas fa-calendar-times"></i>
                删除时间{{ report.deletedAt ? formatDate(report.deletedAt) : '—' }}
              </span>
              <span class="report-card-meta-item">
                <i class="fas fa-user-times"></i>
                删除人{{ report.deletedByUserId !== undefined && report.deletedByUserId !== null ? `用户 #${report.deletedByUserId}` : '—' }}
              </span>
            </template>
            <template v-if="report.type === 'comparison' || report.type === 'secondary_comparison'">
              <span class="report-card-meta-item">
                <i class="fas fa-cubes"></i>
                {{ report.summary?.taskCount || 0 }} 个任务对比
              </span>
            </template>
            <template v-else-if="report.type === 'benchmark'">
              <!-- INT-483：Benchmark 报告无用例统计，展示占位文案（快照详情在报告查看页） -->
              <span class="report-card-meta-item">
                <i class="fas fa-trophy"></i>
                排行快照报告
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

    <!-- 无数据提示：按当前视图 Tab 判断（加载中不显示，避免与加载条并存误导） -->
    <div v-if="!loading && reportSections.length === 0" class="no-data">
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
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'
import "../../assets/styles/tasks/filter-sort.css"
import { computed, ref } from 'vue';
import { ReportStatus, PermissionPoint } from '@/domain/enums';
import type { Report } from '../../domain';
import { useHistoryReports, REPORT_TABS } from './historyReports';
import { useAuthStore } from '../../store/authStore';
import { benchmarkReportsPort } from '../../composables/benchmark/benchmarkReportsPort';
import BenchmarkReportPublishModal from '../../components/benchmark-report/BenchmarkReportPublishModal.vue';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import FavoriteTrashBar from '../../components/common/FavoriteTrashBar.vue';
import VisibilityBadge from '../../components/common/visibility/VisibilityBadge.vue';
import { VISIBILITY_FILTER_OPTIONS, canEditResource } from '../../composables/visibility/useVisibility';
import AlgorithmFilter from '../../components/algorithm/AlgorithmFilter.vue';
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
  // INT-215/S4：回收站态批量恢复/彻底删除
  handleBatchRestore,
  handleBatchPurge,
  viewReport,
  editReport,
  deleteReport,
  publishReport,
  // 收藏 / 回收站（INT-141）
  favoriteOnly,
  trashMode,
  visibilityFilter,
  handleVisibilityFilterChange,
  toggleTrashMode,
  // INT-215：收藏筛选切换（FavoriteTrashBar）
  handleReportFavoriteFilterChange,
  loadReports,
  loadTabCounts,
  isFavorite,
  handleToggleFavorite,
  handleRestoreReport,
  handlePurgeReport
} = useHistoryReports();

// ===== INT-483：发布 Benchmark 报告（调子卡1 POST /benchmarks/reports）=====
/** 发布入口按权限显隐（benchmark:report:publish；admin * 通配已放行） */
const { hasPermission: can } = useAuthStore();
const canPublishBenchmarkReport = computed(() => can(PermissionPoint.BENCHMARK_REPORT_PUBLISH));
const benchmarkPublishVisible = ref(false);
const benchmarkSubmitting = ref(false);

function openBenchmarkPublish() {
  benchmarkPublishVisible.value = true;
}

async function handleBenchmarkPublish(payload: { name: string; description?: string; suite?: string; category?: string; source?: string }) {
  benchmarkSubmitting.value = true;
  try {
    await benchmarkReportsPort.publish(payload);
    benchmarkPublishVisible.value = false;
    showToast('success', 'Benchmark 报告发布成功');
    // 跨组件状态同步：发布成功后报告列表刷新（新 benchmark 报告立即可见）+ Tab 计数刷新
    await Promise.all([loadReports(), loadTabCounts()]);
  } catch (e: any) {
    showToast('error', '发布 Benchmark 报告失败: ' + (e?.message || '未知错误'));
  } finally {
    benchmarkSubmitting.value = false;
  }
}

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

// 报告类型选项（domain ReportType 后端原值，与 historyReports.ts COMPARISON_REPORT_TYPES 对齐；
// INT-483：新增 benchmark 类型筛选）
const REPORT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'comparison', label: '对比报告' },
  { value: 'secondary_comparison', label: '二次对比报告' },
  { value: 'task', label: '任务报告' },
  { value: 'benchmark', label: 'Benchmark 报告' },
];

const REPORT_STATUS_OPTIONS = [
  { value: ReportStatus.DRAFT, label: '草稿' },
  { value: ReportStatus.PUBLISHED, label: '已发布' },
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

function handleAlgorithmFilterChange(value: string | number) {
  filters.value.algorithmType = String(value);
  handleFilterChange();
}
</script>

<style scoped>@import './HistoryReports.css';

/* INT-290 加载指示（对齐 A/B 域 loading bar 方案） */
.history-reports-loading-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    margin-bottom: var(--spacing-lg);
    background: color-mix(in srgb, var(--primary-color) 5%, transparent);
    border-radius: var(--border-radius-lg);
    color: var(--text-secondary);
    font-size: 14px;
}

.history-reports-loading-bar .loading-spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

/* INT-483：发布 Benchmark 报告按钮（页头右侧） */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.benchmark-publish-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background-color: var(--primary-color); /* 去掉 hex 回退：--primary-color 已定义（#ff6a00） */
  border-color: var(--primary-color);
  color: var(--color-white);
  white-space: nowrap;
}

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
