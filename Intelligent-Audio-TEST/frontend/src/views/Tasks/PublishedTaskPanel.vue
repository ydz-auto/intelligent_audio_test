<template>
  <div class="published-task-panel">
    <!-- 列表（筛选排序由 Tasks 页共享筛选栏承载，绑定同一 usePublishedTasks 实例） -->
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
              <span v-if="ptItem.sourceTaskId">来源任务 #{{ ptItem.sourceTaskId }}</span>
              <span v-if="ptItem.publishedAt">发布于 {{ formatDate(ptItem.publishedAt) }}</span>
              <span v-if="ptItem.publishedBy">发布人 {{ ptItem.publishedBy }}</span>
            </div>
          </div>
          <div class="pt-card-actions">
            <button v-if="can(PermissionPoint.PUBLISHED_TASK_EXECUTE)" class="btn btn-primary btn-sm" :disabled="ptItem.status === 'archived' || pt.actionLoading" @click="handleExecute(ptItem)">
              <i class="fas fa-play"></i> 执行
            </button>
            <button class="btn btn-secondary btn-sm" :disabled="pt.actionLoading" @click="toggleDetail(ptItem)">
              <i class="fas fa-history"></i> {{ expandedId === ptItem.id ? '收起' : '版本' }}
            </button>
            <button v-if="can(PermissionPoint.PUBLISHED_TASK_VERSION)" class="btn btn-secondary btn-sm" :disabled="ptItem.status === 'archived' || pt.actionLoading" @click="handleCreateVersion(ptItem)">
              <i class="fas fa-plus-circle"></i> 新版本
            </button>
            <button class="btn btn-secondary btn-sm" :disabled="pt.actionLoading" @click="handleRename(ptItem)">
              <i class="fas fa-edit"></i> 重命名
            </button>
            <button v-if="can(PermissionPoint.PUBLISHED_TASK_ARCHIVE)" class="btn btn-danger btn-sm" :disabled="ptItem.status === 'archived' || pt.actionLoading" @click="handleArchive(ptItem)">
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
            <h4 class="pt-detail-title">
              <i class="fas fa-file-import"></i>
              {{ pt.detail?.hasTaskSnapshot ? '任务详情（发布时冻结 · 不可变）' : '来源任务（发布时取自该日常任务）' }}
            </h4>
            <!-- INT-303：有 taskSnapshot 时按冻结数据渲染（源任务/源用例改动不再影响本版本） -->
            <template v-if="pt.detail?.hasTaskSnapshot">
              <div class="pt-detail-row" v-if="taskSnapshot">
                <span class="pt-detail-name">{{ taskSnapshot.task?.name || pt.detail?.name }}</span>
                <span class="pt-card-status" v-if="taskSnapshot.task?.algorithmType">{{ taskSnapshot.task.algorithmType }}</span>
                <span class="pt-detail-time">用例 {{ taskSnapshot.cases?.length ?? 0 }}</span>
                <span class="pt-detail-time" v-if="taskSnapshot.task?.tags?.length">标签 {{ taskSnapshot.task.tags.join('、') }}</span>
                <button class="btn btn-primary btn-sm" @click="taskSnapshotOpen = true">
                  <i class="fas fa-eye"></i> 查看冻结任务详情
                </button>
              </div>
            </template>
            <!-- 存量版本（发布时未冻结任务详情）：沿用来源任务摘要，并标注历史版本 -->
            <template v-else>
              <div class="pt-detail-row">
                <span class="pt-detail-name">{{ pt.detail?.sourceTaskName }}</span>
                <span class="pt-card-status" :class="pt.detail?.sourceTaskStatus">{{ statusText(pt.detail?.sourceTaskStatus || '') }}</span>
                <span class="pt-detail-time" v-if="pt.detail?.sourceTaskTotalCases != null">用例 {{ pt.detail?.sourceTaskCompletedCases ?? 0 }}/{{ pt.detail?.sourceTaskTotalCases }}</span>
              </div>
              <div class="pt-legacy-banner">
                <i class="fas fa-clock-rotate-left"></i>
                历史版本（发布时未冻结任务详情）：任务详情按来源任务当前数据展示，源用例被编辑/删除后可能失真；执行按引用轨还原（源用例需存在）。
              </div>
            </template>
          </div>

          <div class="pt-detail-section">
            <h4 class="pt-detail-title"><i class="fas fa-file-archive"></i> 冻结报告（发布时快照 · 不可变）</h4>
            <div class="pt-detail-row" v-if="pt.detail?.reportSnapshot">
              <span class="pt-detail-name">{{ pt.detail.reportSnapshot.name }}</span>
              <span class="pt-detail-time">用例 {{ pt.detail.reportSnapshot.summary.completedCases }}/{{ pt.detail.reportSnapshot.summary.totalCases }}</span>
              <span class="pt-detail-time">通过率 {{ formatPassRate(pt.detail.reportSnapshot.summary.passRate) }}</span>
              <button class="btn btn-primary btn-sm" @click="openReportSnapshot">
                <i class="fas fa-eye"></i> 查看冻结报告
              </button>
            </div>
            <div class="pt-detail-row" v-else>该版本无冻结报告（发布时源任务无已完成报告）</div>
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

    <!-- 冻结任务详情弹窗（INT-303：按冻结数据渲染，不 join 现库） -->
    <TaskSnapshotModal
      v-if="taskSnapshotOpen && taskSnapshot"
      :snapshot="taskSnapshot"
      @close="taskSnapshotOpen = false"
    />

    <!-- 命名弹窗（重命名 / 新版本命名） -->
    <PublishedTaskNameModal
      v-if="nameModal.visible"
      :title="nameModal.title"
      :label="nameModal.label"
      :hint="nameModal.hint"
      :initial-value="nameModal.initialValue"
      :placeholder="nameModal.placeholder"
      confirm-text="确定"
      @close="nameModal.visible = false"
      @confirm="handleNameModalConfirm"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * PublishedTaskPanel —— 已发布任务面板（INT-298：迁入 Tasks 页「已发布任务」页签）。
 *
 * 能力与原独立页 PublishedTasks.vue 完全一致（发布弹窗 / 版本链 / 冻结报告快照
 * ReportSnapshotModal / 冻结任务详情 TaskSnapshotModal / benchmark 勾选 / 执行跳转），
 * 视图内功能不降级；筛选状态由宿主（Tasks 页共享筛选栏）注入的 usePublishedTasks
 * 实例承载。操作按钮按权限点显隐（对齐 V9.7.10）。
 */
import { ref, computed, reactive, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { usePublishedTasks, PublishedTaskStatusEnum } from '../../composables/publishedTask/usePublishedTasks';
import { tasksPort } from '../../composables/task/tasksPort';
import { useNotification } from '../../composables/modal/useNotification';
import { useModalControl } from '../../composables/modal/useModal';
import { MODAL_TYPES } from '../../composables/modal/constants';
import { useAuthStore } from '../../store/authStore';
import { BenchmarkCategoryLabels, type BenchmarkCategoryType, PermissionPoint } from '../../domain/enums';
import type { Task } from '../../domain/model/task';
import type { PublishedTaskItem } from '../../domain/model/publishedTask';
import PublishTaskModal from '../../components/published-task/PublishTaskModal.vue';
import ReportSnapshotModal from '../../components/published-task/ReportSnapshotModal.vue';
import TaskSnapshotModal from '../../components/published-task/TaskSnapshotModal.vue';
import PublishedTaskNameModal from '../../components/published-task/PublishedTaskNameModal.vue';

const props = defineProps<{
  /** 宿主注入的已发布任务 Application 状态（Tasks 页共享筛选栏与面板同源） */
  pt: ReturnType<typeof usePublishedTasks>;
}>();

const router = useRouter();
const pt = props.pt;
const notification = useNotification();
const modal = useModalControl();
const { hasPermission: can } = useAuthStore();

const expandedId = ref<number | null>(null);
const publishModalVisible = ref(false);
const presetSourceTaskId = ref<number | null>(null);
const reportSnapshotOpen = ref(false);
const taskSnapshotOpen = ref(false);
const dailyTasks = ref<Task[]>([]);

// ===== 命名弹窗状态（重命名 / 新版本共用）=====
const nameModal = reactive({
  visible: false,
  mode: 'rename' as 'rename' | 'createVersion',
  title: '',
  label: '',
  hint: '',
  placeholder: '',
  initialValue: '',
  ptItem: null as PublishedTaskItem | null,
});

function openNameModal(payload: {
  mode: 'rename' | 'createVersion';
  ptItem: PublishedTaskItem;
  title: string;
  label: string;
  hint?: string;
  placeholder?: string;
  initialValue?: string;
}) {
  nameModal.mode = payload.mode;
  nameModal.ptItem = payload.ptItem;
  nameModal.title = payload.title;
  nameModal.label = payload.label;
  nameModal.hint = payload.hint || '';
  nameModal.placeholder = payload.placeholder || '';
  nameModal.initialValue = payload.initialValue || '';
  nameModal.visible = true;
}

async function handleNameModalConfirm({ name }: { name: string }) {
  const item = nameModal.ptItem;
  if (!item) return;
  nameModal.visible = false;
  if (nameModal.mode === 'rename') {
    try {
      await pt.rename(item.id, name);
      notification.success('任务名称已更新');
    } catch (error: any) {
      notification.error(error?.message || '重命名失败');
    }
    return;
  }
  try {
    await pt.createVersion(item.id, undefined, name || undefined);
    await pt.fetchList();
    if (expandedId.value === item.id) {
      pt.detail = await pt.fetchDetail(item.id);
    }
    notification.success('新版本创建成功');
  } catch (error: any) {
    notification.error(error?.message || '创建新版本失败');
  }
}

const sourceTaskId = computed(() =>
  pt.detail?.sourceTaskId ?? (pt.detail?.snapshotConfig as any)?.sourceTaskId ?? null
);

/** INT-303：任务详情冻结体（有 taskSnapshot 时版本详情按冻结数据渲染） */
const taskSnapshot = computed(() =>
  (pt.detail?.snapshotConfig as any)?.taskSnapshot ?? null
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

/** 打开发布弹窗（INT-298：由 Tasks 页头部/工具栏入口调用，expose 供宿主触发） */
async function openPublishModal() {
  presetSourceTaskId.value = null;
  // 拉取日常任务作为来源候选（可发布状态由弹窗过滤）
  try {
    const data = await tasksPort.getAll({ page: 1, perPage: 100 });
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
    notification.success('已发布任务创建成功');
  } catch (error: any) {
    notification.error(error?.message || '发布失败，请稍后重试');
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
  const detail = await pt.fetchDetail(ptItem.id);
  // 竞态防护：等待期间已切换到其它卡片或收起时，丢弃本次结果
  if (expandedId.value !== ptItem.id) return;
  if (!detail) {
    expandedId.value = null;
    pt.detail = null;
    notification.error('加载版本详情失败，请稍后重试');
    return;
  }
  pt.detail = detail;
}

function openReportSnapshot() {
  reportSnapshotOpen.value = true;
}

// ---------- 执行 ----------

async function handleExecute(ptItem: PublishedTaskItem) {
  if (ptItem.status === 'archived') {
    notification.warning('已归档任务禁止执行，请先创建新版本');
    return;
  }
  let confirmed: unknown = null;
  try {
    confirmed = await modal.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '执行确认',
      content: `将按版本 v${ptItem.version} 的快照创建新的日常任务「${ptItem.name}」，创建后前往任务详情页。是否继续？`,
      confirmText: '创建日常任务',
    });
  } catch {
    confirmed = null; // 异常路径兜底：视为取消
  }
  if (!confirmed) return;
  try {
    const result = await pt.execute(ptItem.id);
    if (result?.taskId) {
      // INT-208 裁定：执行成功后跳转新日常任务详情页（对齐设计文档 §12.2）
      notification.success(`日常任务已创建（ID: ${result.taskId}），即将前往任务详情`);
      router.push({ name: 'taskDetail', params: { id: String(result.taskId) } });
    }
  } catch (error: any) {
    notification.error(error?.message || '创建日常任务失败');
  }
}

// ---------- 新版本 ----------

function handleCreateVersion(ptItem: PublishedTaskItem) {
  openNameModal({
    mode: 'createVersion',
    ptItem,
    title: '创建新版本',
    label: '新版本名称',
    hint: '留空沿用当前版本名称',
    placeholder: ptItem.name,
    initialValue: '',
  });
}

// ---------- 归档 ----------

async function handleArchive(ptItem: PublishedTaskItem) {
  let confirmed: unknown = null;
  try {
    confirmed = await modal.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '归档确认',
      content: `确定归档「${ptItem.name}」v${ptItem.version} 吗？归档后不可直接执行。`,
      confirmText: '归档',
    });
  } catch {
    confirmed = null; // 异常路径兜底：视为取消
  }
  if (!confirmed) return;
  try {
    await pt.archive(ptItem.id);
    notification.success('任务已归档');
  } catch (error: any) {
    notification.error(error?.message || '归档失败');
  }
}

// ---------- 重命名 ----------

function handleRename(ptItem: PublishedTaskItem) {
  openNameModal({
    mode: 'rename',
    ptItem,
    title: '重命名',
    label: '新的任务名称',
    hint: '作用于整个版本链',
    initialValue: ptItem.name,
  });
}

onMounted(() => {
  pt.fetchList();
});

defineExpose({ openPublishModal });
</script>

<style scoped>
.published-task-panel {
  padding: 0;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--border-radius-md);
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
  color: var(--color-white);
}

.btn-primary:hover {
  opacity: 0.88;
}

.btn-primary:disabled {
  background-color: var(--color-gray-300);
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--background-secondary, #f0f0f0);
  color: var(--foreground);
}

.btn-secondary:hover {
  background-color: var(--color-gray-300);
}

.btn-danger {
  background-color: var(--color-red-100);
  color: var(--color-red-600);
}

.btn-danger:hover {
  background-color: var(--color-red-200);
}

.pt-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pt-card {
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--border-radius-xl);
  padding: 14px 16px;
  box-shadow: 0 1px 3px color-mix(in srgb, var(--color-black) 4%, transparent);
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
  background: var(--color-orange-100);
  color: var(--primary-color, #ff6a00);
  font-size: 12px;
  font-weight: 700;
  border-radius: var(--border-radius-full);
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
  border-radius: var(--border-radius-full);
  background: var(--color-slate-100);
  color: var(--color-slate-500);
}

.pt-card-status.published,
.pt-card-status.completed {
  background: var(--color-green-100);
  color: var(--color-green-600);
}

.pt-card-status.archived {
  background: var(--color-slate-100);
  color: var(--color-slate-400);
}

.pt-card-status.failed {
  background: var(--color-red-100);
  color: var(--color-red-600);
}

.pt-card-status.running {
  background: var(--color-blue-100);
  color: var(--color-blue-600);
}

.pt-card-version-count {
  font-size: 12px;
  color: var(--color-slate-400);
}

.pt-card-current {
  font-size: 11px;
  color: var(--color-green-600);
  background: var(--color-green-100);
  border-radius: var(--border-radius-full);
  padding: 1px 6px;
}

.pt-benchmark-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: var(--border-radius-full);
  background: var(--color-purple-100);
  color: var(--color-purple-600);
  white-space: nowrap;
}

.pt-card-desc {
  margin-top: 6px;
  font-size: 13px;
  color: var(--color-gray-500);
}

.pt-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-gray-400);
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
  color: var(--color-gray-600);
  padding: 5px 8px;
  background: var(--color-slate-50);
  border-radius: var(--border-radius-md);
  flex-wrap: wrap;
}

.pt-detail-name {
  font-weight: 500;
  color: var(--color-gray-800);
}

.pt-detail-time {
  color: var(--color-gray-400);
  font-size: 12px;
}

.pt-detail-source {
  color: var(--color-slate-400);
  font-size: 12px;
}

/* INT-303：存量版本（发布时未冻结任务详情）历史标注 */
.pt-legacy-banner {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 6px 10px;
  background: var(--color-amber-50);
  border: 1px solid var(--color-amber-200);
  border-radius: var(--border-radius-md);
  font-size: 12px;
  color: var(--color-amber-800);
}

.pt-legacy-banner i {
  color: var(--color-amber-500);
}

.pt-empty {
  text-align: center;
  padding: 48px 16px;
  color: var(--color-gray-400);
  background: var(--color-slate-50);
  border: 1px dashed var(--color-slate-200);
  border-radius: var(--border-radius-xl);
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
  color: var(--color-gray-500);
}
</style>
