<template>
  <section
    id="composition"
    class="cc"
    :class="{ 'cc--expand': variant === 'expand' }"
    aria-labelledby="composition-title"
  >
    <!-- 标题行：组成 + 只读 + 摘要（§8.2 线框） -->
    <header class="cc-header">
      <h4 id="composition-title" class="cc-title">组成</h4>
      <span class="cc-readonly-badge">只读</span>
      <span class="cc-desc">合并后任务的来源结果结构</span>
      <div v-if="showToolbar" class="cc-summary">
        <span class="cc-summary-chip">来源 {{ sourceTaskCount }} 个任务</span>
        <span class="cc-summary-chip">结果 {{ summary.total }} 条</span>
        <span v-if="summary.failed > 0" class="cc-summary-chip cc-summary-chip--danger">
          失败 {{ summary.failed }}
        </span>
        <span v-if="summary.unevaluated > 0" class="cc-summary-chip">
          未评估 {{ summary.unevaluated }}
        </span>
      </div>
    </header>

    <!-- §7 失效态：源结果已删除（missing=true）——顶部 Alert（--warning）+「只看失效」。
         与执行 / 评估筛选同一套 filterCompositionTree 语义，不另造筛选。 -->
    <div v-if="showToolbar && summary.missing > 0" class="cc-alert" role="alert">
      <i class="fas fa-triangle-exclamation cc-alert-icon"></i>
      <span class="cc-alert-text">
        {{ summary.missing }} 条源结果已失效（源任务或结果已被删除），仅保留溯源记录
      </span>
      <button
        type="button"
        class="cc-btn cc-alert-action"
        data-testid="composition-only-missing"
        :aria-pressed="onlyMissing ? 'true' : 'false'"
        @click="toggleOnlyMissing"
      >
        {{ onlyMissing ? '查看全部结果' : '只看失效' }}
      </button>
    </div>

    <!-- 工具行：四视图 + 用例层组织 + 执行/评估筛选 + 全部展开/收起（§3.2/§4.2）。
         加载中 / 补拉失败 / 无来源记录时只有骨架或空态，不渲染无数据的工具行（§7）。 -->
    <div v-if="showToolbar" class="cc-toolbar">
      <ContainerViewSwitcher
        :view="view"
        aria-label="组成视图切换"
        @update:view="(v) => (view = v)"
      />
      <PickCaseOrgControls
        :org="org"
        :sub-view="subView"
        :fallback-only="!hasOrgData"
        :hint="hasOrgData ? null : undefined"
        @update:org="(v) => (org = v)"
        @update:sub-view="(v) => (subView = v)"
      />
    </div>

    <div v-if="showToolbar" class="cc-toolbar cc-toolbar--filters">
      <label class="cc-filter">
        <span class="cc-filter-label">执行状态</span>
        <select v-model="execFilter" class="cc-select">
          <option value="all">全部状态</option>
          <option value="completed">已完成</option>
          <option value="failed">已失败</option>
          <option value="stopped">已停止</option>
        </select>
      </label>
      <label class="cc-filter">
        <span class="cc-filter-label">评估状态</span>
        <select v-model="evalFilter" class="cc-select">
          <option value="all">全部</option>
          <option value="evaluated">已评估</option>
          <option value="unevaluated">未评估</option>
        </select>
      </label>
      <div class="cc-toolbar-actions">
        <button type="button" class="cc-btn" data-layout-btn @click="expandAll">全部展开</button>
        <button type="button" class="cc-btn" data-layout-btn @click="collapseAll">全部收起</button>
      </div>
    </div>

    <!-- §4.6 降级期提示：执行 / 评估任一降级即显示，字段落地后不再出现（会话内可关闭） -->
    <div v-if="showToolbar && degraded && !degradedDismissed" class="cc-hint" role="note">
      <i class="fas fa-circle-info"></i>
      <span>结果级执行 / 评估状态待后端补字段，当前按用例状态显示</span>
      <div
        role="button"
        tabindex="0"
        class="cc-hint-close"
        aria-label="关闭提示"
        @click="dismissDegradedHintBar"
        @keydown.enter.prevent="dismissDegradedHintBar"
      >
        <i class="fas fa-times"></i>
      </div>
    </div>

    <!-- §5 文案纪律：容器内出现失败条目是正常业务态，不得出现「异常」「失败任务不可合并」等误导表述 -->
    <p v-if="showToolbar && summary.failed > 0" class="cc-note">
      仅执行失败 / 部分失败的任务也可被挑选合并，失败条目按原状态呈现
    </p>

    <!-- 加载骨架（§10.2：树骨架 3 层） -->
    <div v-if="loading" class="cc-skeleton" data-testid="composition-skeleton" aria-hidden="true">
      <div v-for="row in 3" :key="row" class="cc-skeleton-row" :style="{ paddingLeft: `${(row - 1) * 16}px` }">
        <span class="cc-skeleton-dot"></span>
        <span class="cc-skeleton-bar"></span>
        <span class="cc-skeleton-count"></span>
      </div>
    </div>

    <!-- 组成加载失败（§7：仅落点③ 补拉失败；详情侧 source 异常一律静默不渲染本区） -->
    <div v-else-if="error" class="cc-empty">
      <i class="fas fa-triangle-exclamation"></i>
      <p class="cc-empty-title">组成加载失败</p>
      <button type="button" class="cc-btn" data-layout-btn @click="emit('retry')">重试</button>
    </div>

    <!-- 无来源记录（200 且 groups=[] 的关系行缺失异常态，§7） -->
    <div v-else-if="sourceTaskCount === 0" class="cc-empty">
      <i class="fas fa-diagram-project"></i>
      <p class="cc-empty-title">该任务没有合并来源记录</p>
      <p class="cc-empty-desc">若它是历史合并任务，来源关系可能在合并功能上线前生成</p>
    </div>

    <!-- 筛选无命中（§7） -->
    <div v-else-if="filteredRoots.length === 0" class="cc-empty">
      <i class="fas fa-filter-circle-xmark"></i>
      <p class="cc-empty-title">无符合筛选条件的来源结果</p>
      <button v-if="filtersActive" type="button" class="cc-btn" data-layout-btn @click="resetFilters">
        重置筛选
      </button>
    </div>

    <!-- 只读树（同源四视图；只读=无复选框、无移除钮，展开/收起照常） -->
    <div v-else class="cc-tree">
      <CartTree
        :roots="filteredRoots"
        :selected="EMPTY_SELECTION"
        :expanded-keys="expandedKeys"
        :manageable="false"
        :readonly="true"
        :composition-meta="entryMap"
        @toggle-expand="toggleExpand"
        @trace="(resultId) => emit('trace', resultId)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/layouts/main.css'

/**
 * ContainerComposition —— 容器详情「组成」区（INT-1833 · 规范 18 §3.2/§4/§8.2/§12.1）。
 *
 * 首屏主区，紧跟任务信息卡：只读四视图（任务视图默认｜用例｜设备｜结果类型）呈现
 * 「合并后的任务长什么样」。树复用购物车 `CartTree`（readonly + compositionMeta），
 * 层级 / 计数 / 图标与购物车逐项一致——四视图构建由 `compositionTree.buildCompositionView`
 * 转调 P0 `cartTree.buildCartView`，组成区不另造一套树（同源不变量 §0.3）。
 *
 * 只读语义（§4.4）：容器是既成事实，不渲染复选框、无「移除该组」；改动走「复用本次结果重新挑选」。
 * 筛选（§5）纯客户端：命中叶保留 + 祖先保留 + 分支计数按命中集重算，不改层级与展开态。
 * 纯 props，取数在宿主（容器详情详情接口，零额外请求）。
 */
import { computed, ref } from 'vue';
import CartTree from './CartTree.vue';
import ContainerViewSwitcher from './ContainerViewSwitcher.vue';
import PickCaseOrgControls from './PickCaseOrgControls.vue';
import { collectCartNodeKeys, type CartOrgDim, type CartOrgSubView, type CartTreeNode, type CartViewMode } from './cartTree';
import {
  buildCompositionView,
  dismissDegradedHint,
  filterCompositionTree,
  isCompositionDegraded,
  isDegradedHintDismissed,
  organizeCompositionCases,
  summarizeComposition,
  type CompositionViewOptions,
} from './compositionTree';
import type {
  CompositionEntry,
  CompositionEvaluationFilter,
  CompositionExecutionFilter,
} from '../../../domain/model/containerComposition';

const props = withDefaults(defineProps<{
  /** 组成条目（容器详情 + source 装配，§4.3 详情侧零额外请求） */
  entries: CompositionEntry[];
  /** 加载中（骨架；容器识别未完成前宿主不渲染本区） */
  loading?: boolean;
  /** 加载失败（落点③ 页签行展开补拉失败时由宿主注入 → 空态 + 重试） */
  error?: boolean;
  /** 来源任务数（source.groups.length；0 = 关系行缺失异常态 → 无来源记录空态） */
  sourceTaskCount?: number;
  /**
   * 呈现形态：`detail` = 容器详情首屏主区（卡片）；`expand` = 挑选合并页签行展开
   * （落点③，无卡片外框，树区滚动上限 420px，§8.4）。
   */
  variant?: 'detail' | 'expand';
}>(), {
  loading: false,
  error: false,
  sourceTaskCount: 0,
  variant: 'detail',
});

const emit = defineEmits<{
  /** 叶行「溯源」：宿主跳源任务详情 */
  (e: 'trace', resultId: number): void;
  /** 加载失败重试（宿主注入；P3 详情侧不单独取数，保留契约） */
  (e: 'retry'): void;
}>();

defineOptions({ name: 'ContainerComposition' });

/** 只读树不消费选择态（不渲染复选框，handler 只为满足必填 props） */
const EMPTY_SELECTION: ReadonlySet<number> = new Set();

const view = ref<CartViewMode>('task');
/** 用例层组织为组成区会话态，四视图共享（§3.2） */
const org = ref<CartOrgDim>('group');
const subView = ref<CartOrgSubView>('flat');
/** 工具行筛选（§5，纯客户端） */
const execFilter = ref<string>('all');
const evalFilter = ref<string>('all');
/** §7「只看失效」：与执行 / 评估筛选同一套 filterCompositionTree 语义 */
const onlyMissing = ref(false);
const expandedKeys = ref<ReadonlySet<string>>(new Set<string>());
/** 降级期提示关闭态：会话内一次性（模块级状态，切视图 / 重挂组件不再冒出来） */
const degradedDismissed = ref(isDegradedHintDismissed());

function dismissDegradedHintBar() {
  dismissDegradedHint();
  degradedDismissed.value = true;
}

const entryMap = computed<ReadonlyMap<number, CompositionEntry>>(
  () => new Map(props.entries.map((e) => [e.resultId, e])),
);

const viewOptions = computed<CompositionViewOptions>(() => ({
  org: org.value,
  subView: subView.value,
}));

/** 全量摘要（头部计数按源结果全量，不随筛选变化） */
const summary = computed(() => summarizeComposition(props.entries));

/** 真实组织字段在场（分组名 / 标签）→ 组织控件不显示兜底提示（§4.2）。
 *  以用例层组织的实际产物判定：分组视图无真实分组名且标签视图只落「未设置标签」兜底桶
 *  → 条目确实没有组织字段，才允许保留兜底提示。 */
const hasOrgData = computed(() => {
  if (props.entries.length === 0) return false;
  const groupBuckets = organizeCompositionCases(props.entries, 'group', 'flat');
  const tagBuckets = organizeCompositionCases(props.entries, 'tag', 'flat');
  return [...groupBuckets, ...tagBuckets].some((g) => !g.muted);
});

/** 降级期提示判定（任一执行 / 评估状态取自用例行，§4.6） */
const degraded = computed(() => isCompositionDegraded(props.entries));

const filtersActive = computed(
  () => execFilter.value !== 'all' || evalFilter.value !== 'all' || onlyMissing.value,
);

/** 工具行 / 摘要徽章只在有数据可操作时出现：加载中 → 骨架；补拉失败 / 无来源记录 → 空态（§7） */
const showToolbar = computed(
  () => !props.loading && !props.error && props.sourceTaskCount > 0,
);

/** 四视图树（同源 P0 builder）→ 纯客户端筛选（祖先保留、计数重算） */
const filteredRoots = computed<CartTreeNode[]>(() => {
  const roots = buildCompositionView(view.value, props.entries, viewOptions.value);
  return filterCompositionTree(
    roots,
    execFilter.value as CompositionExecutionFilter,
    evalFilter.value as CompositionEvaluationFilter,
    entryMap.value,
    onlyMissing.value ? 'missing' : 'all',
  );
});

/** §7 Alert 操作：只看失效 ↔ 查看全部结果 */
function toggleOnlyMissing() {
  onlyMissing.value = !onlyMissing.value;
}

function expandAll() {
  expandedKeys.value = new Set(collectCartNodeKeys(filteredRoots.value));
}

function collapseAll() {
  expandedKeys.value = new Set<string>();
}

function toggleExpand(key: string) {
  const next = new Set(expandedKeys.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedKeys.value = next;
}

function resetFilters() {
  execFilter.value = 'all';
  evalFilter.value = 'all';
  onlyMissing.value = false;
}
</script>

<style scoped>
/* 全部取语义令牌（规范 18 §9.2/§10.4），深浅同一套；不新增全局 css、不硬编码颜色/圆角/阴影 */
.cc {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 24px;
  padding: 16px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-sm);
}

.cc-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.cc-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}

.cc-readonly-badge {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 11px;
}

.cc-desc {
  font-size: 12px;
  color: var(--muted-foreground);
}

.cc-summary {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.cc-summary-chip {
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--muted);
  color: var(--foreground);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.cc-summary-chip--danger {
  border-color: var(--destructive);
  background: var(--destructive-light);
  color: var(--destructive);
}

.cc-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.cc-toolbar--filters {
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}

.cc-filter {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted-foreground);
}

.cc-select {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--card);
  color: var(--foreground);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
}

.cc-select:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 1px;
}

.cc-toolbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.cc-btn {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--card);
  color: var(--foreground);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
}

.cc-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.cc-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--warning);
  border-radius: var(--radius-control);
  background: var(--warning-light);
  color: var(--warning);
  font-size: 12px;
}

.cc-hint-close {
  margin-left: auto;
  padding: 0 4px;
  cursor: pointer;
  color: inherit;
}

/* §7 失效 Alert：warning 系语义令牌，深浅两套自动成立 */
.cc-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--warning);
  border-radius: var(--radius-control);
  background: var(--warning-light);
  color: var(--foreground);
  font-size: 12px;
}

.cc-alert-icon {
  flex-shrink: 0;
  color: var(--warning);
}

.cc-alert-text {
  min-width: 0;
}

.cc-alert-action {
  flex-shrink: 0;
  margin-left: auto;
  color: var(--warning);
  border-color: var(--warning);
}

.cc-alert-action[aria-pressed='true'] {
  background: var(--warning-light);
  border-color: var(--warning);
  color: var(--warning);
}

/* §5 文案：失败条目是正常业务态（不得出现「异常 / 不可合并」） */
.cc-note {
  margin: 0;
  font-size: 11px;
  color: var(--muted-foreground);
}

.cc-skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}

.cc-skeleton-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cc-skeleton-dot,
.cc-skeleton-bar,
.cc-skeleton-count {
  display: inline-block;
  border: 1px solid var(--border);
  border-radius: var(--radius-tag);
  background: var(--muted);
}

.cc-skeleton-dot {
  width: 14px;
  height: 14px;
}

.cc-skeleton-bar {
  width: 160px;
  height: 14px;
}

.cc-skeleton-count {
  width: 48px;
  height: 14px;
}

.cc-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 16px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-card);
  color: var(--muted-foreground);
  text-align: center;
}

.cc-empty i {
  font-size: 28px;
  color: var(--muted-foreground);
}

.cc-empty-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.cc-empty-desc {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

.cc-tree {
  max-height: 560px;
  overflow-y: auto;
  padding-right: 4px;
}

/* 落点③（挑选合并页签行展开，§8.3/§8.4）：外层已由展开区承载卡片背景，这里只保留内容；
   展开区整体高度上限 420px 内滚动（单一滚动容器，树区不再单独滚动），行本体不撑破列表。 */
.cc--expand {
  margin-top: 0;
  padding: 0;
  max-height: 420px;
  overflow-y: auto;
  background: transparent;
  border: none;
  box-shadow: none;
}

.cc--expand .cc-tree {
  max-height: none;
  overflow: visible;
  padding-right: 0;
}
</style>
