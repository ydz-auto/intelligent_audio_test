<template>
  <div class="published-tasks-view">
    <!-- 页面标题 -->
    <section class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-bookmark"></i>
          已发布任务
        </h2>
        <p class="page-description">从日常任务发布、管理不可变版本快照，支持执行/归档/重命名</p>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" :disabled="pt.actionLoading" @click="openPublishModal">
          <i class="fas fa-bookmark"></i> 发布任务
        </button>
      </div>
    </section>

    <!-- 筛选栏 -->
    <section class="filter-section">
      <input
        type="text"
        class="search-input"
        placeholder="搜索任务名称、说明..."
        v-model="pt.filters.keyword"
        @input="handleFilterChange"
      />
      <div class="filter-item">
        <label>状态：</label>
        <select v-model="pt.filters.status" @change="handleFilterChange">
          <option v-for="opt in pt.statusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div class="filter-item">
        <label>类型：</label>
        <select v-model="pt.filters.type" @change="handleFilterChange">
          <option value="all">全部类型</option>
          <option value="e2e">端到端测试</option>
          <option value="api">API测试</option>
        </select>
      </div>
      <div class="filter-item">
        <label>时间：</label>
        <select v-model="pt.filters.timeRange" @change="handleFilterChange">
          <option value="all">全部时间</option>
          <option value="today">今日</option>
          <option value="yesterday">昨日</option>
          <option value="week">近7天</option>
          <option value="month">近30天</option>
          <option value="custom">自定义</option>
        </select>
      </div>
      <div class="filter-item custom-range" v-if="pt.filters.timeRange === 'custom'">
        <input type="date" v-model="pt.filters.customRange.start" @change="handleFilterChange" />
        <span>至</span>
        <input type="date" v-model="pt.filters.customRange.end" @change="handleFilterChange" />
      </div>
      <div class="filter-item sort-item" @click="pt.toggleSort('publishedAt')">
        发布时间 <i class="fas" :class="sortIcon('publishedAt')"></i>
      </div>
    </section>

    <!-- 列表 -->
    <section class="pt-list">
      <div v-if="pt.loading" class="pt-empty">加载中...</div>
      <div v-else-if="pt.items.length === 0" class="pt-empty">
        <i class="fas fa-bookmark"></i>
        <p>暂无已发布任务</p>
        <p class="pt-empty-hint">从日常任务列表发布，沉淀可复用、可追踪的任务资产</p>
      </div>

      <div v-for="ptItem in pt.items" :key="ptItem.id" class="pt-card">
        <div class="pt-card-head">
          <div class="pt-card-main">
            <div class="pt-card-title-row">
              <span class="pt-version-badge">v{{ ptItem.version }}</span>
              <span class="pt-card-name" :title="ptItem.name">{{ ptItem.name }}</span>
              <span class="pt-card-status" :class="ptItem.status">{{ statusText(ptItem.status) }}</span>
              <span class="pt-benchmark-badge" v-if="ptItem.benchmark" title="参与 Benchmark 排行（实测轨数据源）">Benchmark</span>
              <span class="pt-card-version-count" v-if="(ptItem.versionCount ?? 1) > 1">共 {{ ptItem.versionCount }} 个版本</span>
              <span class="pt-card-current" v-if="ptItem.isCurrent">当前</span>
            </div>
            <div class="pt-card-desc" v-if="ptItem.description">{{ ptItem.description }}</div>
            <div class="pt-card-meta">
              <span>类型：{{ typeText(ptItem.type) }}</span>
              <span v-if="ptItem.sourceTaskId">来源任务 #{{ ptItem.sourceTaskId }}</span>
              <span v-if="ptItem.publishedAt">发布于 {{ formatDate(ptItem.publishedAt) }}</span>
              <span v-if="ptItem.publishedBy">发布人 {{ ptItem.publishedBy }}</span>
            </div>
          </div>
          <div class="pt-card-actions">
            <button class="btn btn-primary btn-sm" :disabled="ptItem.status === 'archived' || pt.actionLoading" @click="handleExecute(ptItem)">
              <i class="fas fa-play"></i> 执行
            </button>
            <button class="btn btn-secondary btn-sm" :disabled="pt.actionLoading" @click="toggleDetail(ptItem)">
              <i class="fas fa-history"></i> {{ expandedId === ptItem.id ? '收起' : '版本' }}
            </button>
            <button class="btn btn-secondary btn-sm" :disabled="ptItem.status === 'archived' || pt.actionLoading" @click="handleCreateVersion(ptItem)">
              <i class="fas fa-plus-circle"></i> 新版本
            </button>
            <button class="btn btn-secondary btn-sm" :disabled="pt.actionLoading" @click="handleRename(ptItem)">
              <i class="fas fa-edit"></i> 重命名
            </button>
            <button class="btn btn-danger btn-sm" :disabled="ptItem.status === 'archived' || pt.actionLoading" @click="handleArchive(ptItem)">
              <i class="fas fa-archive"></i> 归档
            </button>
          </div>
        </div>

        <!-- 版本历史 / 来源任务 / 冻结报告 / 执行记录 -->
        <div v-if="expandedId === ptItem.id" class="pt-detail">
          <div class="pt-detail-section">
            <h4 class="pt-detail-title"><i class="fas fa-history"></i> 版本历史（共 {{ pt.detail?.versions?.length ?? 0 }} 个版本）</h4>
            <div v-for="v in pt.detail?.versions || []" :key="v.id" class="pt-detail-row">
              <span class="pt-version-badge">v{{ v.version }}</span>
              <span class="pt-card-status" :class="v.status">{{ statusText(v.status) }}</span>
              <span class="pt-detail-time">{{ formatDate(v.publishedAt) }}</span>
              <span class="pt-detail-source" v-if="v.sourceTaskId">来源任务 #{{ v.sourceTaskId }}</span>
            </div>
          </div>

          <div class="pt-detail-section" v-if="benchmarkInfo">
            <h4 class="pt-detail-title"><i class="fas fa-ranking-star"></i> Benchmark 标记（发布时冻结）</h4>
            <div class="pt-detail-row">
              <span class="pt-benchmark-badge">Benchmark</span>
              <span class="pt-detail-name">参与 Benchmark 排行（实测轨数据源）</span>
              <span class="pt-detail-time" v-if="benchmarkInfo.suite">测试集：{{ benchmarkInfo.suite }}</span>
              <span class="pt-detail-time" v-if="benchmarkInfo.categoryLabel">类别：{{ benchmarkInfo.categoryLabel }}</span>
            </div>
          </div>

          <div class="pt-detail-section" v-if="sourceTaskId">
            <h4 class="pt-detail-title"><i class="fas fa-file-import"></i> 来源任务（发布时取自该日常任务）</h4>
            <div class="pt-detail-row">
              <span class="pt-detail-name">{{ pt.detail?.sourceTaskName }}</span>
              <span class="pt-card-status" :class="pt.detail?.sourceTaskStatus">{{ statusText(pt.detail?.sourceTaskStatus || '') }}</span>
              <span class="pt-detail-time" v-if="pt.detail?.sourceTaskTotalCases != null">用例 {{ pt.detail?.sourceTaskCompletedCases ?? 0 }}/{{ pt.detail?.sourceTaskTotalCases }}</span>
            </div>
          </div>

          <div class="pt-detail-section">
            <h4 class="pt-detail-title"><i class="fas fa-file-archive"></i> 冻结报告（发布时快照 · 不可变）</h4>
            <div class="pt-detail-row" v-if="pt.detail?.reportSnapshot">
              <span class="pt-detail-name">{{ pt.detail.reportSnapshot.name }}</span>
              <span class="pt-detail-time">用例 {{ pt.detail.reportSnapshot.summary.completedCases }}/{{ pt.detail.reportSnapshot.summary.totalCases }}</span>
              <span class="pt-detail-time">通过率 {{ formatPassRate(pt.detail.reportSnapshot.summary.passRate) }}</span>
              <button class="btn btn-primary btn-sm" @click="openReportSnapshot(pt.detail.reportSnapshot)">
                <i class="fas fa-eye"></i> 查看冻结报告
              </button>
            </div>
            <div class="pt-detail-row" v-else>该版本发布时未冻结执行数据（无报告）</div>
          </div>

          <div class="pt-detail-section" v-if="(pt.detail?.executionHistory || []).length > 0">
            <h4 class="pt-detail-title"><i class="fas fa-play-circle"></i> 执行记录（按冻结快照执行生成的日常任务）</h4>
            <div v-for="exec in pt.detail?.executionHistory || []" :key="exec.taskId" class="pt-detail-row">
              <span class="pt-version-badge">v{{ exec.version }}</span>
              <span class="pt-detail-name">{{ exec.taskName }}</span>
              <span class="pt-card-status" :class="exec.status">{{ statusText(exec.status) }}</span>
              <span class="pt-detail-time">用例 {{ exec.completedCases }}/{{ exec.totalCases }}</span>
              <span class="pt-detail-time">{{ formatDate(exec.createdAt) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pt-pagination" v-if="pt.total > 0">
        <button class="btn btn-secondary btn-sm" :disabled="pt.page <= 1" @click="pt.setPage(pt.page - 1)">
          <i class="fas fa-chevron-left"></i>
        </button>
        <span class="pt-page-info">第 {{ pt.page }} / {{ Math.max(pt.pages, 1) }} 页 · 共 {{ pt.total }} 条</span>
        <button class="btn btn-secondary btn-sm" :disabled="pt.page >= pt.pages" @click="pt.setPage(pt.page + 1)">
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
    </section>

    <!-- 发布弹窗 -->
    <PublishTaskModal
      v-if="publishModalVisible"
      :tasks="dailyTasks"
      :submitting="pt.actionLoading"
      :preset-source-task-id="presetSourceTaskId"
      @close="closePublishModal"
      @confirm="handlePublishConfirm"
    />

    <!-- 冻结报告弹窗 -->
    <ReportSnapshotModal
      v-if="reportSnapshotOpen && pt.detail?.reportSnapshot"
      :snapshot="pt.detail.reportSnapshot"
      @close="reportSnapshotOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { usePublishedTasks, PublishedTaskStatusEnum } from '../../composables/publishedTask/usePublishedTasks';
import { tasksApi } from '../../infrastructure/api';
import { BenchmarkCategoryLabels, type BenchmarkCategoryType } from '../../domain/enums';
import type { Task } from '../../domain/model/task';
import type { PublishedTaskItem } from '../../domain/model/publishedTask';
import PublishTaskModal from '../../components/published-task/PublishTaskModal.vue';
import ReportSnapshotModal from '../../components/published-task/ReportSnapshotModal.vue';

const pt = usePublishedTasks();

const expandedId = ref<number | null>(null);
const publishModalVisible = ref(false);
const presetSourceTaskId = ref<number | null>(null);
const reportSnapshotOpen = ref(false);
const dailyTasks = ref<Task[]>([]);

const sourceTaskId = computed(() =>
  pt.detail?.sourceTaskId ?? (pt.detail?.snapshotConfig as any)?.sourceTaskId ?? null
);

/** 详情的 Benchmark 展示信息（行级标记 + 快照冻结的测试集/类别） */
const benchmarkInfo = computed(() => {
  if (!pt.detail?.benchmark) return null;
  const snapshot = pt.detail.snapshotConfig as any;
  const category = snapshot?.benchmarkCategory as string | undefined | null;
  return {
    suite: (snapshot?.benchmarkSuite as string | undefined | null) || '',
    categoryLabel: category ? (BenchmarkCategoryLabels[category as BenchmarkCategoryType] ?? category) : '',
  };
});

function handleFilterChange() {
  pt.page = 1;
  pt.fetchList();
}

function sortIcon(field: string): string {
  if (pt.filters.sort.field !== field) return 'fa-sort';
  return pt.filters.sort.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down';
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    [PublishedTaskStatusEnum.PUBLISHED]: '已发布',
    [PublishedTaskStatusEnum.ARCHIVED]: '已归档',
    completed: '已完成',
    failed: '失败',
    stopped: '已停止',
    pending: '待执行',
    running: '执行中',
  };
  return map[status] || status;
}

function typeText(type: string): string {
  const map: Record<string, string> = { api: 'API 测试', e2e: 'E2E 测试' };
  return map[type] || type;
}

function formatDate(val?: string | null): string {
  if (!val) return '-';
  const d = new Date(val);
  if (Number.isNaN(d.getTime())) return val;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatPassRate(val?: number | null): string {
  if (val == null) return '0%';
  if (val <= 1) return `${(val * 100).toFixed(1)}%`;
  return `${Number(val).toFixed(1)}%`;
}

// ---------- 发布 ----------

async function openPublishModal() {
  presetSourceTaskId.value = null;
  // 拉取日常任务作为来源候选（可发布状态由弹窗过滤）
  try {
    const data = await tasksApi.getAll({ page: 1, perPage: 100 });
    dailyTasks.value = (data as any).items ?? [];
  } catch (error) {
    console.error('Failed to fetch tasks for publish modal:', error);
    dailyTasks.value = [];
  }
  publishModalVisible.value = true;
}

function closePublishModal() {
  presetSourceTaskId.value = null;
  publishModalVisible.value = false;
}

async function handlePublishConfirm(payload: {
  sourceTaskId: number;
  name: string;
  description?: string;
  publishReason?: string;
  benchmark: boolean;
  benchmarkSuite?: string;
  benchmarkCategory?: string;
}) {
  try {
    await pt.publish(
      payload.sourceTaskId,
      payload.name,
      payload.description,
      payload.publishReason,
      { benchmark: payload.benchmark, benchmarkSuite: payload.benchmarkSuite, benchmarkCategory: payload.benchmarkCategory }
    );
    closePublishModal();
    await pt.fetchList();
    alert('已发布任务创建成功');
  } catch (error: any) {
    alert(error?.message || '发布失败，请稍后重试');
  }
}

// ---------- 详情 ----------

async function toggleDetail(ptItem: PublishedTaskItem) {
  if (expandedId.value === ptItem.id) {
    expandedId.value = null;
    pt.detail = null;
    return;
  }
  expandedId.value = ptItem.id;
  pt.detail = await pt.fetchDetail(ptItem.id);
}

function openReportSnapshot(snapshot: any) {
  if (snapshot) {
    pt.detail = { ...(pt.detail as any), reportSnapshot: snapshot };
    reportSnapshotOpen.value = true;
  }
}

// ---------- 执行 ----------

async function handleExecute(ptItem: PublishedTaskItem) {
  if (ptItem.status === 'archived') {
    alert('已归档任务禁止执行，请先创建新版本');
    return;
  }
  if (!confirm(`将按版本 v${ptItem.version} 的快照创建新的日常任务「${ptItem.name}」，创建后到任务列表启动执行。是否继续？`)) return;
  try {
    const result = await pt.execute(ptItem.id);
    if (result?.taskId) {
      alert(`日常任务已创建（ID: ${result.taskId}），请到任务列表启动执行`);
    }
  } catch (error: any) {
    alert(error?.message || '创建日常任务失败');
  }
}

// ---------- 新版本 ----------

async function handleCreateVersion(ptItem: PublishedTaskItem) {
  const name = prompt('新版本名称（留空沿用当前版本名称）：', ptItem.name);
  if (name === null) return;
  try {
    await pt.createVersion(ptItem.id, undefined, name.trim() || undefined);
    await pt.fetchList();
    if (expandedId.value === ptItem.id) {
      pt.detail = await pt.fetchDetail(ptItem.id);
    }
    alert('新版本创建成功');
  } catch (error: any) {
    alert(error?.message || '创建新版本失败');
  }
}

// ---------- 归档 ----------

async function handleArchive(ptItem: PublishedTaskItem) {
  if (!confirm(`确定归档「${ptItem.name}」v${ptItem.version} 吗？归档后不可直接执行。`)) return;
  try {
    await pt.archive(ptItem.id);
    alert('任务已归档');
  } catch (error: any) {
    alert(error?.message || '归档失败');
  }
}

// ---------- 重命名 ----------

async function handleRename(ptItem: PublishedTaskItem) {
  const name = prompt('新的任务名称（作用于整个版本链）：', ptItem.name);
  if (name === null) return;
  try {
    await pt.rename(ptItem.id, name.trim());
    alert('任务名称已更新');
  } catch (error: any) {
    alert(error?.message || '重命名失败');
  }
}

onMounted(() => {
  pt.fetchList();
});
</script>

<style scoped>
.published-tasks-view {
  padding: 4px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.page-description {
  margin: 4px 0 0;
  color: var(--foreground-muted, #6b7280);
  font-size: 13px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-sm {
  padding: 5px 10px;
  font-size: 12px;
}

.btn-primary {
  background-color: var(--primary-color, #ff6a00);
  color: #fff;
}

.btn-primary:hover {
  opacity: 0.88;
}

.btn-primary:disabled {
  background-color: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--background-secondary, #f0f0f0);
  color: #333;
}

.btn-secondary:hover {
  background-color: #e0e0e0;
}

.btn-danger {
  background-color: #fee2e2;
  color: #dc2626;
}

.btn-danger:hover {
  background-color: #fecaca;
}

.filter-section {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  margin-bottom: 16px;
}

.search-input {
  flex: 1;
  min-width: 200px;
  padding: 7px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #4b5563;
}

.filter-item select {
  padding: 6px 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
}

.custom-range input {
  padding: 5px 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 12px;
}

.sort-item {
  cursor: pointer;
  user-select: none;
}

.sort-item:hover {
  color: var(--primary-color, #ff6a00);
}

.pt-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pt-card {
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.pt-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.pt-card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pt-version-badge {
  display: inline-block;
  background: #fff1e6;
  color: var(--primary-color, #ff6a00);
  font-size: 12px;
  font-weight: 700;
  border-radius: 10px;
  padding: 2px 8px;
  white-space: nowrap;
}

.pt-card-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--foreground, #1f2937);
}

.pt-card-status {
  display: inline-block;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #eef2f7;
  color: #64748b;
}

.pt-card-status.published,
.pt-card-status.completed {
  background: #dcfce7;
  color: #16a34a;
}

.pt-card-status.archived {
  background: #f1f5f9;
  color: #94a3b8;
}

.pt-card-status.failed {
  background: #fee2e2;
  color: #dc2626;
}

.pt-card-status.running {
  background: #dbeafe;
  color: #2563eb;
}

.pt-card-version-count {
  font-size: 12px;
  color: #94a3b8;
}

.pt-card-current {
  font-size: 11px;
  color: #16a34a;
  background: #dcfce7;
  border-radius: 8px;
  padding: 1px 6px;
}

.pt-benchmark-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
  background: #ede9fe;
  color: #7c3aed;
  white-space: nowrap;
}

.pt-card-desc {
  margin-top: 6px;
  font-size: 13px;
  color: #6b7280;
}

.pt-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
}

.pt-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex-shrink: 0;
}

.pt-detail {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color, #e5e7eb);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pt-detail-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pt-detail-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground, #1f2937);
  display: flex;
  align-items: center;
  gap: 6px;
}

.pt-detail-title i {
  color: var(--primary-color, #ff6a00);
}

.pt-detail-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #4b5563;
  padding: 5px 8px;
  background: #f8fafc;
  border-radius: 6px;
  flex-wrap: wrap;
}

.pt-detail-name {
  font-weight: 500;
  color: #1f2937;
}

.pt-detail-time {
  color: #9ca3af;
  font-size: 12px;
}

.pt-detail-source {
  color: #94a3b8;
  font-size: 12px;
}

.pt-empty {
  text-align: center;
  padding: 48px 16px;
  color: #9ca3af;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
  border-radius: 10px;
}

.pt-empty i {
  font-size: 32px;
  margin-bottom: 8px;
}

.pt-empty-hint {
  font-size: 12px;
  margin-top: 4px;
}

.pt-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.pt-page-info {
  font-size: 13px;
  color: #6b7280;
}
</style>
