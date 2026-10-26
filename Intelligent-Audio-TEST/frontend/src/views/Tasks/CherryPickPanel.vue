<template>
  <div class="cpp">
    <!-- 页内四步向导（§10 #4 裁定：非独立路由页） -->
    <CherryPickWizard
      v-if="wizardOpen"
      :preset-task-ids="wizardPresetTaskIds"
      :initial-step="wizardInitialStep"
      @close="closeWizard"
      @checked-out="onCheckedOut"
    />

    <template v-else>
      <!-- Actions：开始挑选 / 打开购物车 / 管理挑选集（task:cherry_pick；algo_engineer 只读可见列表，链隐藏） -->
      <div class="cpp-actions">
        <div class="cpp-actions-left">
          <button v-if="canPick" class="cpp-btn cpp-btn-primary" @click="startWizard()">
            <i class="fas fa-plus"></i> 开始挑选
          </button>
          <button v-if="canPick" class="cpp-btn" @click="cartDrawerState.open()">
            <i class="fas fa-cart-shopping"></i> 打开购物车
            <span v-if="cartCount > 0" class="cpp-badge">{{ cartCount }}</span>
          </button>
          <div v-if="canPick" class="cpp-pick-sets">
            <button class="cpp-btn" @click="setsPopoverOpen = !setsPopoverOpen">
              <i class="fas fa-layer-group"></i> 管理挑选集
            </button>
            <div v-if="setsPopoverOpen" class="cpp-sets-popover">
              <div v-if="sets.length === 0" class="cpp-sets-empty">暂无挑选集</div>
              <div v-for="s in sets" :key="s.setId" class="cpp-set-row">
                <span class="cpp-set-name" :title="s.name">{{ s.name }}</span>
                <span class="cpp-count">{{ s.itemCount }} 条</span>
                <button class="cpp-btn cpp-btn-sm" @click="restoreSet(s.setId)"><i class="fas fa-undo"></i> 恢复</button>
                <button class="cpp-btn cpp-btn-sm cpp-btn-danger" @click="onDeleteSet(s.setId)"><i class="fas fa-trash"></i></button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 合并方式 facet + stats 徽章行（§11-1） -->
      <div class="cpp-facet-row">
        <div class="cpp-facet">
          <button
            v-for="opt in MERGE_FACET_OPTIONS"
            :key="opt.value"
            class="cpp-btn cpp-btn-sm"
            :class="{ active: containers.filters.mergeType === opt.value }"
            @click="setFacet(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
        <div class="cpp-stats" v-if="containers.stats">
          <span class="cpp-stat">合并容器 <b>{{ containers.stats.total }}</b></span>
          <span class="cpp-stat">整任务合并 <b>{{ containers.stats.whole }}</b></span>
          <span class="cpp-stat">结果挑选 <b>{{ containers.stats.picked }}</b></span>
        </div>
      </div>

      <!-- 容器列表 -->
      <div v-if="containers.loading" class="cpp-loading">
        <div class="loading-spinner"></div>
        <p>正在加载挑选合并任务…</p>
      </div>
      <div v-else-if="containers.items.length === 0" class="cpp-empty">
        <i class="fas fa-cart-shopping"></i>
        <p>暂无挑选合并任务</p>
        <p class="cpp-empty-hint">点击「开始挑选」，从任务/用例/设备/结果类型任一层级勾选执行结果，加入购物车后预览、合并</p>
        <button v-if="canPick" class="cpp-btn cpp-btn-primary" @click="startWizard()">
          <i class="fas fa-plus"></i> 开始挑选
        </button>
      </div>
      <div v-else class="cpp-list">
        <div v-for="ct in containers.items" :key="ct.id" class="cpp-card">
          <TaskCard
            :task="mapContainerTask(ct)"
            :actions="taskActions"
            :is-favorite="isFavorite(Number(ct.id)) || false"
            :show-checkbox="false"
            :show-config="false"
            @action="(event: any) => emit('task-action', event)"
            @name-updated="(payload: any) => emit('name-updated', payload)"
            @favorite-toggle="(task: any) => emit('task-action', { action: { id: isFavorite(Number(task.id)) ? 'unfavorite' : 'favorite' }, task })"
          />

          <!-- 溯源展开（按合并方式自适应）：
               整任务合并（whole）= 源任务列表（保持现状）；
               结果挑选（picked）= 组成区树（INT-1834 · 规范 18 §3 落点③：同源四视图，
               任务视图默认；首次展开补 1 次 GET /tasks/{id}，按 taskId 缓存） -->
          <div class="cpp-source-toggle" role="button" tabindex="0" @click="toggleSource(ct)" @keydown.enter.prevent="toggleSource(ct)" @keydown.space.prevent="toggleSource(ct)">
            <i class="fas fa-source-branch"></i>
            {{ expanded.has(Number(ct.id)) ? '收起溯源' : '源结果溯源' }}
            <i class="fas cpp-source-icon" :class="expanded.has(Number(ct.id)) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
          </div>
          <div v-if="expanded.has(Number(ct.id))" class="cpp-source-body">
            <!-- 结果挑选：组成区树（落点③） -->
            <ContainerTraceExpand
              v-if="ct.mergeType !== 'whole'"
              :task-id="Number(ct.id)"
              :summary="containerSummary(ct)"
              @trace="openSourceTrace"
            />
            <!-- 整任务合并：源任务列表（不变） -->
            <template v-else>
              <div v-if="sourceLoadingByTask[Number(ct.id)]" class="cpp-loading-hint"><i class="fas fa-spinner fa-spin"></i> 正在加载溯源…</div>
              <template v-else-if="(ct.sourceTasks?.length ?? 0) > 0">
                <div class="cpp-source-head">源任务列表（{{ ct.sourceTasks.length }} 个）</div>
                <div v-for="st in ct.sourceTasks" :key="st.id" class="cpp-source-row">
                  <span class="cpp-source-name"><i class="fas fa-source-branch"></i> {{ st.name }}</span>
                  <span class="cpp-source-cases">结果 {{ st.resultCount ?? st.sourceResultCount ?? '-' }} 条</span>
                </div>
              </template>
              <!-- INT-552：溯源加载失败可见错误（含重试），与「暂无来源」真实空态区分 -->
              <div v-else-if="sourceErrorByTask[Number(ct.id)]" class="cpp-source-error">
                <i class="fas fa-exclamation-triangle"></i>
                <span>溯源加载失败，请重试</span>
                <button class="cpp-source-retry source-retry-btn" @click="loadSource(Number(ct.id))"><i class="fas fa-redo"></i> 重试</button>
              </div>
              <div v-else class="cpp-source-row"><span class="cpp-source-cases">该合并任务暂无来源记录</span></div>
            </template>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <PaginationComponent
        v-if="containers.total > 0"
        :current-page="containers.page"
        :page-size="containers.perPage"
        :total-items="containers.total"
        :total-pages="containers.pages"
        @prev-page="containers.setPage(containers.page - 1)"
        @next-page="containers.setPage(containers.page + 1)"
        @go-to-page="containers.setPage"
        @page-size-change="containers.setPageSize"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/progress.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

/**
 * CherryPickPanel —— 挑选合并统一容器页签（INT-577 M2/M3）。
 *
 * 统一容器列表（merged ∪ cherry_pick，§11-1）+ 合并方式 facet + stats 徽章行 +
 * Actions（开始挑选/打开购物车/管理挑选集）+ 溯源展开：picked（结果挑选）行展开即
 * **组成区树**（INT-1834 · 规范 18 §3 落点③，与容器详情同源四视图，首次展开补拉 1 次
 * `GET /tasks/{id}` 并按 taskId 缓存）；whole（整任务合并）行展开仍是源任务列表。
 * 页内四步向导（§10 #4）：替换列表区，含批量「加入挑选」预选入口。
 * RBAC（§8）：列表/购物车角标 task:read 只读可见；写链（开始挑选/增删/预览/下单）task:cherry_pick。
 */
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import TaskCard from '../../components/task/TaskCard.vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import CherryPickWizard from '../../components/task/pick/CherryPickWizard.vue';
import ContainerTraceExpand from '../../components/task/pick/ContainerTraceExpand.vue';
import { cherryPickApi } from '../../infrastructure/api';
import { usePickCart } from '../../composables/task/usePickCart';
import { useCartDrawerState } from '../../composables/task/cartDrawerState';
import { usePickWizardRequest, requestPickWizard, clearPickWizardRequest } from '../../composables/task/usePickWizardRequest';
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal';
import { useAuthStore } from '../../store/authStore';
import { PermissionPoint } from '../../domain/enums';
import type { Task } from '../../domain/model/task';
import type { MergeTypeFacet } from '../../composables/task/useCherryPickContainers';

const props = defineProps<{
  /** 宿主注入的统一容器列表 Application 状态（useCherryPickContainers 实例） */
  containers: any;
  /** 任务操作定义（与日常任务卡片共用；事件由宿主分发） */
  taskActions: any[];
  /** 收藏行内星标态判定函数（宿主注入） */
  isFavorite: (id: string | number) => boolean;
}>();

const emit = defineEmits<{
  (e: 'task-action', payload: { action: { id: string }; task: any }): void;
  (e: 'name-updated', payload: { taskId: string | number; newName: string }): void;
  (e: 'checked-out', payload: { action: string; taskId?: number }): void;
}>();

const route = useRoute();
const router = useRouter();
const { hasPermission: can } = useAuthStore();
const { cartCount, refreshCart, refreshSets, sets, restoreSetToCart, deleteSet } = usePickCart();
const cartDrawerState = useCartDrawerState();

// 容器列表 Application 状态（props.containers 本地别名，供模板/逻辑统一引用）
const containers = props.containers;

const canPick = computed(() => can(PermissionPoint.TASK_CHERRY_PICK));

const MERGE_FACET_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'whole', label: '整任务合并' },
  { value: 'picked', label: '结果挑选' },
] as const;

const wizardOpen = ref(false);
const wizardPresetTaskIds = ref<(number | string)[]>([]);
/** 直达步骤（「去预览」→ preview；缺省 pick） */
const wizardInitialStep = ref<'pick' | 'cart' | 'preview' | 'checkout'>('pick');
const setsPopoverOpen = ref(false);

/** 溯源展开状态（默认收起；picked 行的组成模型由 ContainerTraceExpand 按 taskId 缓存） */
const expanded = ref<Set<number>>(new Set());
const sourceLoadingByTask = ref<Record<number, boolean>>({});
/** INT-552：整任务合并「源任务列表」加载失败错误态（按卡独立，与「真无来源」空态区分） */
const sourceErrorByTask = ref<Record<number, boolean>>({});

const modalControl = useModalControl();

function setFacet(value: MergeTypeFacet) {
  containers.filters.mergeType = value;
  containers.apply();
  // 合并方式筛选随 URL 态（§2.2 裁定①：merge_type 随 URL）
  const query: Record<string, string> = { ...route.query, tab: 'cherry-picks' } as Record<string, string>;
  if (value !== 'all') query.merge_type = value; else delete query.merge_type;
  router.replace({ query });
}

function startWizard(presetTaskIds?: (number | string)[]) {
  wizardPresetTaskIds.value = presetTaskIds ?? [];
  wizardInitialStep.value = 'pick';
  wizardOpen.value = true;
}

/** 批量「加入挑选」（宿主 Tasks.vue 批量浮条调用）：任务级预选 */
function openWizardWithTasks(taskIds: (number | string)[]) {
  startWizard(taskIds);
}

/** 向导关闭：清共享请求防泄漏（§10 #5 会话级口径；关闭后再挂载不再自开） */
function closeWizard() {
  wizardOpen.value = false;
  clearPickWizardRequest();
}

// P0 修复：批量「加入挑选」/「去预览」经 usePickWizardRequest 共享请求跨导航重挂载存活。
// immediate watch：新面板挂载（含 :key=fullPath 重挂载后的最终实例）即消费请求自开向导；
// 请求在向导关闭/下单前保持置位，避免重挂载中途清掉导致最终实例不自开。
const { pendingRequest } = usePickWizardRequest();
watch(pendingRequest, (req) => {
  if (req) {
    wizardPresetTaskIds.value = req.presetTaskIds ?? [];
    wizardInitialStep.value = req.step ?? 'pick';
    wizardOpen.value = true;
  }
}, { immediate: true });

/**
 * 行展开 / 收起。
 * - picked（结果挑选）：组成区树；数据由 ContainerTraceExpand 首次展开补拉并缓存，本层不请求。
 * - whole（整任务合并）：源任务列表（列表 DTO 的 sourceTasks）；沿用 INT-552 的加载 / 错误态。
 */
function toggleSource(ct: any) {
  const taskId = Number(ct.id);
  const next = new Set(expanded.value);
  const expanding = !next.has(taskId);
  if (expanding) {
    next.add(taskId);
  } else {
    next.delete(taskId);
  }
  expanded.value = next;
  if (expanding && ct.mergeType === 'whole') {
    loadSource(taskId);
  }
}

/** 列表 DTO 的来源计数（补充给展开区，补拉未完成时兜底；缺省 → null 不占位） */
function containerSummary(ct: any) {
  return {
    taskCount: ct.sourceTaskCount ?? null,
    resultCount: ct.sourceResultCount ?? null,
  };
}

/** 组成区叶行「溯源」：打开源任务详情并定位该结果（模态窗可叠层，不离开当前页签；INT-1838 §6） */
function openSourceTrace(payload: { resultId: number; sourceTaskId: number; sourceCaseId?: string | null }) {
  modalControl.open(MODAL_TYPES.TASK_DETAIL, {
    taskId: payload.sourceTaskId,
    focusCaseId: payload.sourceCaseId ?? '',
  });
}

/** 整任务合并行：源任务列表取自列表 DTO；source 端点只用于加载 / 出错态（INT-552） */
async function loadSource(taskId: number) {
  sourceLoadingByTask.value = { ...sourceLoadingByTask.value, [taskId]: true };
  sourceErrorByTask.value = { ...sourceErrorByTask.value, [taskId]: false };
  try {
    await cherryPickApi.getSource(taskId);
  } catch (error) {
    // INT-552：失败保留旧数据 + 可见错误（含重试），空态文案仅真无来源展示
    console.error('Failed to load pick source:', error);
    sourceErrorByTask.value = { ...sourceErrorByTask.value, [taskId]: true };
  } finally {
    sourceLoadingByTask.value = { ...sourceLoadingByTask.value, [taskId]: false };
  }
}

function mapContainerTask(ct: any): Task {
  return {
    ...ct,
    title: ct.name,
    createdAt: ct.createdAt,
  } as Task;
}

function onCheckedOut(payload: { action: string; taskId?: number }) {
  wizardOpen.value = false;
  clearPickWizardRequest();
  emit('checked-out', payload);
}

async function restoreSet(setId: number) {
  try {
    await restoreSetToCart(setId);
  } catch (error: any) {
    console.error(error?.message || '挑选集恢复失败');
  }
}

async function onDeleteSet(setId: number) {
  try {
    await deleteSet(setId);
  } catch (error: any) {
    console.error(error?.message || '删除挑选集失败');
  }
}

// URL 态：wizard=preview 直达预览步骤（购物车抽屉「去预览」）；merge_type 随 URL 恢复 facet
watch(
  () => route.query,
  () => {
    if (route.query.wizard === 'preview') {
      // 转共享请求自开预览向导（:key=fullPath 重挂载下 URL 清参
      // 会再触发重挂载，向导态经 usePickWizardRequest 存活）
      requestPickWizard({ step: 'preview' });
      const query = { ...route.query };
      delete query.wizard;
      router.replace({ query });
    }
    const mt = route.query.merge_type;
    if (mt === 'whole' || mt === 'picked') {
      if (containers.filters.mergeType !== mt) {
        containers.filters.mergeType = mt;
        containers.apply();
      }
    }
  },
  { immediate: true, deep: true },
);

onMounted(() => {
  props.containers.fetchList();
  refreshCart();
  refreshSets();
});

defineExpose({ openWizardWithTasks, startWizard });
</script>

<style scoped>
.cpp { position: relative; }
.cpp-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.cpp-actions-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cpp-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-md);
  background: #fff;
  color: var(--foreground, #1e293b);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cpp-btn:hover { border-color: var(--primary, #ff6a00); color: var(--primary, #ff6a00); }
.cpp-btn.active {
  border-color: var(--primary, #ff6a00);
  background: var(--accent, #fff7ed);
  color: var(--primary, #ff6a00);
}
.cpp-btn-primary {
  background: var(--primary, #ff6a00);
  border-color: var(--primary, #ff6a00);
  color: #fff;
}
.cpp-btn-primary:hover { background: var(--primary-hover, #e55d00); color: #fff; }
.cpp-btn-sm { padding: 4px 10px; font-size: 12px; }
.cpp-btn-danger { border-color: var(--destructive, #dc2626); color: var(--destructive, #dc2626); }
.cpp-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: var(--radius-full);
  background: var(--primary, #ff6a00);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}
.cpp-pick-sets {
  position: relative;
}
.cpp-sets-popover {
  position: absolute;
  top: 110%;
  left: 0;
  z-index: 100;
  min-width: 260px;
  background: #fff;
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.1);
  padding: 8px;
}
.cpp-sets-empty { padding: 12px; text-align: center; color: var(--color-slate-400, #94a3b8); font-size: 13px; }
.cpp-set-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  font-size: 13px;
}
.cpp-set-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cpp-count {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-500, #64748b);
  font-size: 11px;
  font-weight: 500;
}
.cpp-facet-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 8px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--color-slate-100, #f1f5f9);
}
.cpp-facet {
  display: flex;
  align-items: center;
  gap: 4px;
}
.cpp-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--color-slate-500, #64748b);
}
.cpp-stat b { color: var(--primary, #ff6a00); font-size: 14px; }
.cpp-loading,
.cpp-empty {
  padding: 40px 16px;
  text-align: center;
  color: var(--color-slate-400, #94a3b8);
}
.cpp-loading p, .cpp-empty p { margin: 8px 0 4px; }
.cpp-empty i { font-size: 42px; color: var(--color-slate-300, #cbd5e1); }
.cpp-empty-hint { font-size: 13px !important; color: var(--color-slate-400, #94a3b8); margin-bottom: 12px !important; }
.cpp-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cpp-card {
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-xl);
  padding: 12px;
}
.cpp-source-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 4px 0;
  font-size: 13px;
  color: var(--color-slate-600, #475569);
  cursor: pointer;
  user-select: none;
}
.cpp-source-toggle:hover { color: var(--primary, #ff6a00); }
.cpp-source-icon { margin-left: auto; font-size: 11px; }
.cpp-source-body {
  margin-top: 8px;
  padding: 8px 12px;
  /* 语义令牌：深浅两套自动成立（picked 行展开内是组成区树，深色下不能用浅色常量底） */
  background: var(--muted);
  border-radius: var(--radius-md);
}
.cpp-source-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-slate-500, #64748b);
  padding-bottom: 4px;
}
.cpp-source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.cpp-source-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cpp-source-cases { color: var(--color-slate-500, #64748b); font-size: 12px; }
/* INT-552：整任务合并源任务列表加载失败可见错误（含重试） */
.cpp-source-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 13px;
  color: var(--destructive, #dc2626);
}
.source-retry-btn {
  padding: 2px 10px;
  font-size: 12px;
  color: var(--color-primary, #2563eb);
  background: transparent;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-md);
  cursor: pointer;
}
.source-retry-btn:hover {
  border-color: var(--color-primary, #2563eb);
}
.cpp-loading-hint { padding: 8px 0; color: var(--color-slate-400, #94a3b8); font-size: 13px; }
</style>
