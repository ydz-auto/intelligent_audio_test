<template>
  <div class="merged-task-panel cherry-pick-panel">
    <!-- 挑选合并任务列表（复用合并面板交互：TaskCard + 可展开来源分组） -->
    <div class="merged-task-list" v-if="!cherryPick.loading">
      <div v-for="ct in cherryPick.items" :key="ct.id" class="published-card-wrap">
        <TaskCard
          :task="mapCherryPickTask(ct)"
          :actions="taskActions"
          :show-checkbox="false"
          :show-config="false"
          @action="(event: any) => emit('task-action', event)"
          @name-updated="(payload: any) => emit('name-updated', payload)"
        />

        <!-- 源结果溯源列表（默认收起，点击展开；验收 §12.2 溯源） -->
        <div class="merged-source-list" v-if="(ct.id ?? null) !== null && expanded.has(Number(ct.id))">
          <div v-if="sourceLoading" class="loading-hint"><i class="fas fa-spinner fa-spin"></i> 正在加载溯源...</div>
          <template v-else-if="sourceGroups.length > 0">
            <div v-for="group in sourceGroups" :key="group.sourceTaskId" class="merged-source-row">
              <div class="merged-source-row-info">
                <span class="merged-source-row-name" :title="group.sourceTaskName">
                  <i class="fas fa-source-branch"></i> {{ group.sourceTaskName }}
                </span>
                <span class="merged-source-row-cases">结果 {{ group.results.length }} 条</span>
              </div>
            </div>
          </template>
          <div v-else class="merged-source-row">
            <span class="merged-source-row-cases">该挑选合并任务暂无来源记录</span>
          </div>
        </div>
        <div class="merged-source-list" v-else>
          <div class="merged-source-list-title" @click="toggleSource(Number(ct.id))">
            <i class="fas fa-source-branch"></i> 源结果溯源
            <i class="fas merged-source-toggle" :class="expanded.has(Number(ct.id)) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
          </div>
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
import { canEditResource } from '../../composables/visibility/useVisibility';
import type { PickSource } from '../../infrastructure/api/cherryPickApi';
import type { Task } from '../../domain/model/task';

const props = defineProps<{
  /** 宿主注入的挑选合并列表 Application 状态（useCherryPickTasks 实例） */
  cherryPick: any;
  /** 任务操作定义（与日常任务卡片共用；事件由宿主分发） */
  taskActions: any[];
}>();

const emit = defineEmits<{
  (e: 'task-action', payload: { action: { id: string }; task: any }): void;
  (e: 'name-updated', payload: { taskId: string | number; newName: string }): void;
}>();

/** 溯源展开状态（默认收起） */
const expanded = ref<Set<number>>(new Set());
const sourceLoading = ref(false);
const sourceGroups = ref<PickSource['groups']>([]);

function toggleSource(taskId: number) {
  const next = new Set(expanded.value);
  if (next.has(taskId)) {
    next.delete(taskId);
    expanded.value = next;
    return;
  }
  expanded.value = next;
  loadSource(taskId);
}

async function loadSource(taskId: number) {
  sourceLoading.value = true;
  try {
    const source = await cherryPickApi.getSource(taskId);
    sourceGroups.value = source.groups ?? [];
  } catch (error) {
    console.error('Failed to load pick source:', error);
    sourceGroups.value = [];
  } finally {
    sourceLoading.value = false;
  }
}

/** 任务域映射（与合并面板 mapMergedTask 同构）。
 *  INT-467（UX 审计 P3）：显式透传 visibility/createdByUserId + canEdit——
 *  挑选列表内私有任务需展示锁徽标且删除/改名门控随行（不能依赖 ...ct 隐式带过）。 */
function mapCherryPickTask(ct: any): Task {
  return {
    ...ct,
    title: ct.name,
    createdAt: ct.createdAt,
    visibility: ct.visibility ?? undefined,
    createdByUserId: ct.createdByUserId ?? undefined,
    canEdit: canEditResource(ct),
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
</style>
