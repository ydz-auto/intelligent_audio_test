<template>
  <div class="test-reports-view">
    <!-- Toast 提示：Teleport 到全局固定元素容器（对齐 HistoryReports，避免 fixed 包含块被截获） -->
    <teleport to="#global-fixed-elements">
      <div v-if="toast" class="toast-container" :class="`toast-${toast.type}`">
        <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : 'fas fa-info-circle'"></i>
        <span>{{ toast.message }}</span>
      </div>
    </teleport>

    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-file-alt"></i>
          测试历史报告数据
        </h2>
        <p class="page-description">查看测试任务产生的报告数据</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" :disabled="loading" @click="loadReports">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i> 刷新报告
        </button>
      </div>
    </div>

    <!-- 加载态 -->
    <div v-if="loading && reports.length === 0" class="tr-loading-state">
      <div class="tr-loading-spinner"></div>
      <p>正在加载报告...</p>
    </div>

    <!-- 错误态 -->
    <div v-else-if="error" class="tr-error-state">
      <i class="fas fa-exclamation-triangle"></i>
      <h3>加载失败</h3>
      <p>{{ error }}</p>
      <button class="btn btn-primary" @click="loadReports">
        <i class="fas fa-redo"></i> 重试
      </button>
    </div>

    <!-- 空态 -->
    <div v-else-if="reports.length === 0" class="tr-empty-state">
      <i class="fas fa-inbox"></i>
      <h3>暂无报告数据</h3>
      <p>测试任务执行完成后生成的报告将在此展示</p>
    </div>

    <!-- 报告列表 -->
    <template v-else>
      <div class="reports-section">
        <div class="section-header">
          <h3 class="section-title">
            <i class="fas fa-layer-group" style="color: var(--primary-color);"></i>
            报告列表 ({{ total }})
          </h3>
        </div>

        <div v-for="report in reports" :key="report.id" class="card report-card">
          <div class="card-header">
            <div class="report-card-title-wrapper">
              <h3 class="report-card-title">{{ report.name }}</h3>
              <div class="report-card-meta-tags">
                <span class="report-card-type">{{ getReportTypeLabel(report.type) }}</span>
                <span class="report-card-status" :class="report.status === ReportStatus.DRAFT ? 'draft' : 'published'">
                  {{ report.status === ReportStatus.DRAFT ? '草稿' : '已发布' }}
                </span>
                <span v-if="report.taskName" class="report-card-test-type">{{ report.taskName }}</span>
              </div>
            </div>
            <div class="card-actions">
              <button
                class="btn btn-secondary"
                :title="isFavorite(report.id) ? '取消收藏' : '收藏'"
                :style="isFavorite(report.id) ? 'color: var(--favorite-star)' : ''"
                @click.stop="handleToggleFavorite(report)"
              >
                <i :class="isFavorite(report.id) ? 'fas fa-star' : 'far fa-star'"></i>
              </button>
              <button class="btn btn-primary" @click.stop="viewReport(report.id)">
                <i class="fas fa-eye"></i> 查看报告
              </button>
              <button class="btn btn-danger" @click.stop="deleteReport(report.id)">
                <i class="fas fa-trash"></i> 删除
              </button>
            </div>
          </div>
          <div class="card-body">
            <p class="report-card-description">{{ report.description || '暂无摘要' }}</p>
            <div class="report-card-meta">
              <span class="report-card-meta-item">
                <i class="fas fa-calendar-alt"></i>
                {{ formatDate(report.createdAt) }}
              </span>
              <template v-if="report.type === 'comparison' || report.type === 'secondary_comparison'">
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

      <!-- 分页 -->
      <PaginationComponent
        :current-page="currentPage"
        :page-size="pageSize"
        :total-items="total"
        @prev-page="handlePrevPage"
        @next-page="handleNextPage"
        @go-to-page="handleGoToPage"
        @page-size-change="handlePageSizeChange"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ReportStatus } from '@/domain/enums';
import { useTestReports } from './testReports';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';

const {
  reports,
  total,
  currentPage,
  pageSize,
  loading,
  error,
  toast,
  loadReports,
  getReportTypeLabel,
  formatDate,
  viewReport,
  isFavorite,
  handleToggleFavorite,
  deleteReport,
  handlePrevPage,
  handleNextPage,
  handleGoToPage,
  handlePageSizeChange,
} = useTestReports();
</script>

<style scoped>
.test-reports-view {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-lg);
}

.page-header .header-actions {
  display: flex;
  gap: var(--spacing-sm);
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

/* 三态容器：加载 / 错误 / 空（tr- 前缀命名空间，对齐 rv- 方案避免全局泄漏） */
.tr-loading-state,
.tr-error-state,
.tr-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  text-align: center;
}

.tr-loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-slate-200);
  border-top-color: var(--secondary);
  border-radius: 50%;
  animation: tr-spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes tr-spin {
  to { transform: rotate(360deg); }
}

.tr-loading-state p,
.tr-error-state p,
.tr-empty-state p {
  color: var(--text-tertiary);
  margin: 8px 0 24px 0;
}

.tr-error-state h3,
.tr-empty-state h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.tr-error-state i,
.tr-empty-state i {
  font-size: var(--font-size-xxxl);
  margin-bottom: var(--spacing-md);
}

.tr-error-state i {
  color: var(--warning-color);
}

.tr-empty-state i {
  color: var(--text-disabled);
}

/* 列表区 */
.reports-section {
  margin-bottom: var(--spacing-md);
}

.section-header {
  margin-bottom: var(--spacing-sm);
}

.section-title {
  font-size: var(--font-size-md);
  margin: 0;
}

.report-card {
  border: var(--card-border);
  border-radius: var(--border-radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
  background-color: var(--background-primary);
}

.report-card .card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-sm);
  border-bottom: none;
  background: transparent;
}

.report-card-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  margin: 0 0 var(--spacing-xs) 0;
  color: var(--text-primary);
}

.report-card-meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  align-items: center;
}

.report-card-type,
.report-card-status,
.report-card-test-type {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--border-radius-sm);
  background-color: var(--info-light);
  color: var(--info-color);
}

.report-card-status.draft {
  background-color: var(--warning-light);
  color: var(--warning-color);
}

.report-card-actions,
.card-actions {
  display: flex;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

.report-card-description {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  margin: 0 0 var(--spacing-sm) 0;
}

.report-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.report-card-meta-item {
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
