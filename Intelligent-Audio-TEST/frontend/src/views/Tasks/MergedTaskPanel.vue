<template>
  <div class="merged-task-panel">
    <!-- 合并任务列表（对齐 V9.7.10 合并页签：TaskCard + 可展开源任务列表，源行保留完整操作） -->
    <div class="merged-task-list" v-if="!merged.loading">
      <div v-for="mt in merged.items" :key="mt.id" class="published-card-wrap">
        <!-- 任务主体：复用日常任务卡片（标题/状态徽章/按钮位置/尺寸完全一致） -->
        <TaskCard
          :task="mapMergedTask(mt)"
          :actions="taskActions"
          :show-checkbox="false"
          :show-config="false"
          @action="(event: any) => emit('task-action', event)"
          @name-updated="(payload: any) => emit('name-updated', payload)"
        />

        <!-- 源任务列表（默认收起，点击标题展开，支持查看/执行/评估/报告等全部操作） -->
        <div class="merged-source-list" v-if="(mt.sourceTasks?.length ?? 0) > 0">
          <div class="merged-source-list-title" @click="toggleMergedSources(Number(mt.id))">
            <i class="fas fa-object-ungroup"></i> 源任务列表（{{ mt.sourceTasks!.length }} 个）
            <i class="fas merged-source-toggle" :class="expandedMergedSources.has(Number(mt.id)) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
          </div>
          <template v-if="expandedMergedSources.has(Number(mt.id))">
            <div v-for="src in mt.sourceTasks" :key="src.id" class="merged-source-row">
              <div class="merged-source-row-info">
                <span class="merged-source-row-name" :title="src.name">{{ src.name }}</span>
                <span class="merged-source-status" :class="src.status">{{ getStatusText(src.status || '') }}</span>
                <span class="merged-source-row-cases"><i class="fas fa-list-alt"></i>用例 {{ src.completedCases ?? 0 }}/{{ src.totalCases ?? 0 }}</span>
                <span v-if="src.createdAt" class="merged-source-row-time"><i class="fas fa-calendar-alt"></i>{{ formatDate(src.createdAt) }}</span>
              </div>
              <div class="merged-source-row-actions">
                <template v-for="act in taskActions" :key="act.id">
                  <button
                    v-if="!act.show || act.show(src)"
                    class="btn btn-sm"
                    :class="`btn-${act.type}`"
                    :disabled="typeof act.disabled === 'function' ? act.disabled(src) : act.disabled"
                    :title="act.title || act.label"
                    @click="emit('task-action', { action: { id: act.id }, task: src })"
                  >
                    <i v-if="act.icon" :class="`fas ${act.icon}`"></i>
                    {{ act.label }}
                  </button>
                </template>
              </div>
            </div>
          </template>
        </div>
        <div class="merged-source-list empty-source-hint" v-else>
          <div class="merged-source-row">
            <span class="merged-source-row-cases">该合并任务暂无来源任务记录</span>
          </div>
        </div>
      </div>

      <div class="empty-state" v-if="merged.items.length === 0">
        <i class="fas fa-object-group"></i>
        <p>暂无合并任务</p>
        <p class="empty-state-hint">在任务列表勾选多个已完成任务，点击「合并任务」创建</p>
      </div>
    </div>

    <div class="loading-state" v-else>
      <div class="loading-spinner"></div>
      <p>正在加载合并任务...</p>
    </div>

    <!-- 分页 -->
    <PaginationComponent
      v-if="merged.total > 0"
      :current-page="merged.page"
      :page-size="merged.perPage"
      :total-items="merged.total"
      :total-pages="merged.pages"
      @prev-page="handleMergedPage(-1)"
      @next-page="handleMergedPage(1)"
      @go-to-page="handleMergedGoTo"
      @page-size-change="handleMergedPageSize"
    />
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'

/**
 * MergedTaskPanel —— 合并任务面板（INT-298：迁入 Tasks 页「合并任务」页签，对齐 V9.7.10）。
 *
 * 数据源：GET /tasks?merged=true（TaskMergeRelation 存在性判定合并容器，宿主注入
 * useMergedTasks 实例与页面级筛选排序栏同源）。卡片复用 TaskCard；源任务行保留
 * 完整任务操作（V9.7.10 交互口径：查看/执行/评估/报告等），由宿主传入统一 taskActions。
 */
import { ref, onMounted } from 'vue';
import TaskCard from '../../components/task/TaskCard.vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import { useMergedTasks } from '../../composables/task/useMergedTasks';
import { canEditResource } from '../../composables/visibility/useVisibility';
import { formatDate } from '@/utils/utils';
import { getTaskStatusLabel } from '../../domain/constants/reportLabels';
import type { Task } from '../../domain/model/task';

const props = defineProps<{
  /** 宿主注入的合并任务 Application 状态（Tasks 页共享筛选栏与面板同源） */
  merged: ReturnType<typeof useMergedTasks>;
  /** 任务操作定义（与日常任务卡片共用，保证行为一致；事件由宿主分发） */
  taskActions: any[];
}>();

const emit = defineEmits<{
  /** 源任务行/卡片操作分发（统一交宿主 handleTaskAction 处理） */
  (e: 'task-action', payload: { action: { id: string }; task: any }): void;
  /** 合并任务卡片重命名（宿主走日常任务重命名接口后 refresh） */
  (e: 'name-updated', payload: { taskId: string | number; newName: string }): void;
}>();

const merged = props.merged;

/** 源任务列表展开状态（默认收起） */
const expandedMergedSources = ref<Set<number>>(new Set());

function toggleMergedSources(id: number) {
  const next = new Set(expandedMergedSources.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  expandedMergedSources.value = next;
}

/** 合并任务 → TaskCard 数据结构（来源数并入描述，保留完整执行统计，对齐 V9.7.10）。
 *  INT-467（UX 审计 P3）：透传 visibility/createdByUserId + canEdit——合并列表内
 *  私有任务需展示锁徽标且删除/改名门控随行（此前固定形状映射丢弃了这些字段）。 */
function mapMergedTask(mt: any): Task {
  const base = {
    id: mt.id,
    name: mt.name,
    description: mt.description || (mt.sourceTasks?.length ? `合并自 ${mt.sourceTasks.length} 个任务` : ''),
    status: mt.status,
    createdAt: formatDate(mt.createdAt),
    tags: mt.tags || [],
    caseCount: mt.totalCases ?? 0,
    totalCases: mt.totalCases ?? 0,
    completedCases: mt.completedCases ?? 0,
  } as Task;
  return {
    ...base,
    visibility: mt.visibility ?? undefined,
    createdByUserId: mt.createdByUserId ?? undefined,
    canEdit: canEditResource(mt),
  } as Task;
}

function getStatusText(status: string): string {
  return getTaskStatusLabel(status);
}

function handleMergedPage(delta: number) {
  const next = merged.page + delta;
  if (next < 1 || next > merged.pages) return;
  merged.setPage(next);
}

function handleMergedGoTo(p: number) {
  if (p >= 1 && p <= merged.pages) {
    merged.setPage(p);
  }
}

function handleMergedPageSize(size: number) {
  merged.setPageSize(size);
}

/** 页签挂载即拉取（v-else-if 语义：每次切入合并页签重新加载当前筛选下的列表） */
onMounted(() => {
  merged.fetchList();
});
</script>

<style scoped>
/* ===== 合并任务面板（对齐 V9.7.10 样式口径）===== */
.merged-task-list {
  display: flex;
  flex-direction: column;
}

.published-card-wrap {
  margin-bottom: 12px;
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.merged-source-list {
  margin-top: 4px;
  padding: 10px 12px;
  background: var(--color-slate-50, #f8fafc);
  border: 1px dashed var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
}

.merged-source-list-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-slate-600, #475569);
  margin-bottom: 8px;
  cursor: pointer;
  user-select: none;
}

.merged-source-list-title:hover {
  color: var(--primary, #ff6a00);
}

.merged-source-toggle {
  margin-left: auto;
  color: var(--color-slate-400, #94a3b8);
  font-size: 12px;
  transition: transform 0.2s ease;
}

.merged-source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 6px 4px;
  border-bottom: 1px solid var(--color-slate-100, #eef2f7);
}

.merged-source-row:last-child {
  border-bottom: none;
}

.merged-source-row-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
  flex: 1;
}

.merged-source-row-name {
  font-weight: 500;
  color: var(--color-slate-700, #334155);
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.merged-source-row-cases {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-slate-500, #64748b);
  font-size: 12px;
}

.merged-source-row-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-slate-400, #94a3b8);
  font-size: 12px;
}

.merged-source-row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.empty-source-hint .merged-source-row {
  justify-content: flex-start;
  color: var(--color-slate-400, #94a3b8);
  font-size: 13px;
}

.merged-source-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 500;
  background: var(--color-slate-200, #e2e8f0);
  color: var(--color-slate-500, #64748b);
  flex-shrink: 0;
}

.merged-source-status.merged {
  background: var(--color-orange-50);
  color: var(--color-orange-600);
}

.merged-source-status.completed {
  background: var(--color-green-50);
  color: var(--color-emerald-600);
}

.merged-source-status.failed {
  background: var(--color-red-100);
  color: var(--color-red-600);
}
</style>
