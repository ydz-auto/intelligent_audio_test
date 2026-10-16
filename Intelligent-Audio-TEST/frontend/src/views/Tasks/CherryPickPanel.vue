<template>
  <div class="merged-task-panel cherry-pick-panel">
    <!-- 挑选合并任务列表（复用合并面板交互：TaskCard + 可展开来源分组） -->
    <div class="merged-task-list" v-if="!cherryPick.loading">
      <div v-for="ct in cherryPick.items" :key="ct.id" class="published-card-wrap">
        <TaskCard
          :task="mapCherryPickTask(ct)"
          :actions="taskActions"
          :is-favorite="isFavorite(Number(ct.id)) || false"
          :show-checkbox="false"
          :show-config="false"
          @action="(event: any) => emit('task-action', event)"
          @name-updated="(payload: any) => emit('name-updated', payload)"
          @favorite-toggle="(task: any) => emit('task-action', { action: { id: isFavorite(Number(task.id)) ? 'unfavorite' : 'favorite' }, task })"
        />

        <!-- 源结果溯源列表（默认收起，点击标题展开；验收 §12.2 溯源；INT-401：按卡独立缓存，多卡展开互不覆盖） -->
        <div class="merged-source-list" v-if="(ct.id ?? null) !== null">
          <div class="merged-source-list-title" @click="toggleSource(Number(ct.id))">
            <i class="fas fa-source-branch"></i> 源结果溯源
            <i class="fas merged-source-toggle" :class="expanded.has(Number(ct.id)) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
          </div>
          <template v-if="expanded.has(Number(ct.id))">
            <div v-if="sourceLoadingByTask[Number(ct.id)]" class="loading-hint"><i class="fas fa-spinner fa-spin"></i> 正在加载溯源...</div>
            <template v-else-if="(sourcesByTask[Number(ct.id)]?.length ?? 0) > 0">
              <div v-for="group in sourcesByTask[Number(ct.id)]" :key="group.sourceTaskId" class="merged-source-row">
                <div class="merged-source-row-info">
                  <span class="merged-source-row-name" :title="group.sourceTaskName">
                    <i class="fas fa-source-branch"></i> {{ group.sourceTaskName }}
                  </span>
                  <span class="merged-source-row-cases">结果 {{ group.results.length }} 条</span>
                </div>
                <!-- INT-401：引用结果明细 + 缺失标注（引用方案 A 的 missing 场景，§10） -->
                <div class="cp-source-results">
                  <div v-for="res in group.results" :key="res.resultId" class="cp-source-result" :class="{ missing: res.missing }">
                    <span class="cp-source-case">{{ res.sourceCaseId ?? `结果 #${res.resultId}` }}</span>
                    <span v-if="res.missing" class="cp-row-badge missing-badge" title="源结果已被删除，此条引用不可达">
                      <i class="fas fa-exclamation-triangle"></i> 源结果已缺失
                    </span>
                  </div>
                </div>
              </div>
            </template>
            <!-- INT-552：溯源加载失败可见错误（含重试），与「暂无来源」真实空态区分 -->
            <div v-else-if="sourceErrorByTask[Number(ct.id)]" class="merged-source-error">
              <i class="fas fa-exclamation-triangle"></i>
              <span>溯源加载失败：{{ sourceErrorByTask[Number(ct.id)] }}</span>
              <button class="merged-source-retry" @click="loadSource(Number(ct.id))"><i class="fas fa-redo"></i> 重试</button>
            </div>
            <div v-else class="merged-source-row">
              <span class="merged-source-row-cases">该挑选合并任务暂无来源记录</span>
            </div>
          </template>
        </div>
      </div>

      <div class="empty-state" v-if="cherryPick.items.length === 0">
        <i class="fas fa-shopping-cart"></i>
        <p>暂无挑选合并任务</p>
        <p class="empty-state-hint">在任务详情挑选执行结果加入购物车，下单「合并生成新任务」后在此展示</p>
      </div>
    </div>

    <div class="loading-state" v-else>
      <div class="loading-spinner"></div>
      <p>正在加载挑选合并任务...</p>
    </div>

    <!-- 分页 -->
    <PaginationComponent
      v-if="cherryPick.total > 0"
      :current-page="cherryPick.page"
      :page-size="cherryPick.perPage"
      :total-items="cherryPick.total"
      :total-pages="cherryPick.pages"
      @prev-page="cherryPick.setPage(cherryPick.page - 1)"
      @next-page="cherryPick.setPage(cherryPick.page + 1)"
      @go-to-page="cherryPick.setPage"
      @page-size-change="cherryPick.setPageSize"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * CherryPickPanel —— 挑选合并面板（INT-339：任务列表第五页签）。
 *
 * 数据源：GET /tasks?cherry_pick=true（task_cherry_pick_relations 存在性判定，
 * 与合并页签 useMergedTasks 同构）。卡片复用 TaskCard；溯源列表经
 * GET /tasks/cherry-picks/{id}/source 按需展开加载。
 */
import { ref, reactive, onMounted } from 'vue';
import TaskCard from '../../components/task/TaskCard.vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import { cherryPickApi } from '../../infrastructure/api';
import type { PickSource } from '../../infrastructure/api/cherryPickApi';
import type { Task } from '../../domain/model/task';

const props = defineProps<{
  /** 宿主注入的挑选合并列表 Application 状态（useCherryPickTasks 实例） */
  cherryPick: any;
  /** 任务操作定义（与日常任务卡片共用；事件由宿主分发） */
  taskActions: any[];
  /** INT-401：收藏行内星标态判定函数（宿主注入 useFavorites.isFavorite） */
  isFavorite: (id: string | number) => boolean;
}>();

const emit = defineEmits<{
  (e: 'task-action', payload: { action: { id: string }; task: any }): void;
  (e: 'name-updated', payload: { taskId: string | number; newName: string }): void;
}>();

/** 溯源展开状态（默认收起；INT-401：数据按卡独立缓存，多卡同时展开互不覆盖） */
const expanded = ref<Set<number>>(new Set());
const sourceLoadingByTask = ref<Record<number, boolean>>({});
const sourcesByTask = ref<Record<number, PickSource['groups']>>({});
// INT-552：溯源加载失败错误态（原静默清空成「暂无来源」误导文案）
const sourceErrorByTask = ref<Record<number, string>>({});

function toggleSource(taskId: number) {
  const next = new Set(expanded.value);
  if (next.has(taskId)) {
    next.delete(taskId);
  } else {
    next.add(taskId);
    loadSource(taskId);
  }
  expanded.value = next;
}

async function loadSource(taskId: number) {
  sourceLoadingByTask.value = { ...sourceLoadingByTask.value, [taskId]: true };
  const prevError = { ...sourceErrorByTask.value };
  delete prevError[taskId];
  sourceErrorByTask.value = prevError;
  try {
    const source = await cherryPickApi.getSource(taskId);
    sourcesByTask.value = { ...sourcesByTask.value, [taskId]: source.groups ?? [] };
  } catch (error: any) {
    // INT-552：失败保留旧数据 + 可见错误（含重试），空态文案仅真无来源展示
    console.error('Failed to load pick source:', error);
    const err = { ...sourceErrorByTask.value };
    err[taskId] = error?.message || '请重试';
    sourceErrorByTask.value = err;
  } finally {
    sourceLoadingByTask.value = { ...sourceLoadingByTask.value, [taskId]: false };
  }
}

/** 任务域映射（与合并面板 mapMergedTask 同构） */
function mapCherryPickTask(ct: any): Task {
  return {
    ...ct,
    title: ct.name,
    createdAt: ct.createdAt,
  } as Task;
}

onMounted(() => {
  props.cherryPick.fetchList();
});
</script>

<style scoped>
.cherry-pick-panel .empty-state i {
  font-size: 42px;
  color: var(--color-slate-300, #cbd5e1);
}
.loading-hint {
  padding: 8px 16px;
  color: var(--color-slate-400, #94a3b8);
  font-size: 13px;
}
/* INT-552：溯源加载失败错误态（原静默空态文案误导） */
.merged-source-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-amber-100, #fef3c7);
  color: var(--color-amber-800, #92400e);
  border: 1px solid var(--color-amber-300, #fcd34d);
  border-radius: var(--border-radius-md, 8px);
  font-size: 13px;
}
.merged-source-error i { color: var(--color-amber-600, #d97706); }
.merged-source-retry {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--primary, #ff6a00);
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.merged-source-retry:hover { text-decoration: underline; }
/* INT-401：溯源明细（引用结果 + 缺失标注）样式自包含，与合并面板同视觉 token */
.merged-source-list {
  margin-top: 4px;
  padding: 10px 12px;
  background: var(--color-slate-50, #f8fafc);
  border: 1px dashed var(--color-slate-200, #e2e8f0);
  border-radius: 8px;
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
.cp-source-results {
  flex-basis: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 4px 4px 2px;
}
.cp-source-result {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-slate-600, #475569);
  background: var(--color-white, #fff);
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: 6px;
  padding: 2px 8px;
}
.cp-source-result.missing {
  border-color: var(--color-red-300, #fca5a5);
  background: var(--color-red-50, #fef2f2);
}
.cp-source-result .missing-badge {
  color: var(--color-red-600, #dc2626);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
</style>
