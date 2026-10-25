<template>
  <div class="ctr-wrap">
    <!-- 用例节点 → 统一用例卡 compact（§3.8.4/§4.2，INT-1110）；勾选=批量移除选择三态；
         展开 = 设备/result_type 子树（叶行） -->
    <template v-if="node.level === 'case'">
      <PickCaseCard
        :name="node.name"
        :case-id="node.caseId ?? undefined"
        :algorithm-type="node.algorithmType"
        :count="node.count"
        :state="state"
        :open="expanded"
        :readonly="readonly"
        class="ctr-case-card"
        @toggle="emit('toggle-node', node)"
        @toggle-open="emit('toggle-expand', node.key)"
      >
        <!-- §4.3 节点「移除该组」走统一卡行内操作插槽（INT-1103 PickCaseCard 口径）；
             组成区只读（INT-1833）不渲染 -->
        <template #actions>
          <button
            v-if="manageable && !readonly"
            class="ctr-btn ctr-btn-danger"
            @click.stop="emit('remove-group', node)"
          >
            <i class="fas fa-trash"></i> 移除该组
          </button>
        </template>
        <template v-if="expanded">
          <CartTreeNodeRow
            v-for="child in node.children"
            :key="child.key"
            :node="child"
            :selected="selected"
            :expanded-keys="expandedKeys"
            :leaf-meta="leafMeta"
            :manageable="manageable"
            :readonly="readonly"
            :composition-meta="compositionMeta"
            :depth="depth + 1"
            @toggle-node="(n) => emit('toggle-node', n)"
            @toggle-expand="(k) => emit('toggle-expand', k)"
            @toggle-leaf="(id) => emit('toggle-leaf', id)"
            @remove-leaf="(id) => emit('remove-leaf', id)"
            @remove-group="(n) => emit('remove-group', n)"
            @trace="(id) => emit('trace', id)"
          />
        </template>
      </PickCaseCard>
    </template>

    <!-- 普通节点行（非用例节点：任务/用例层组织/组织子组/设备/result_type） -->
    <div v-else class="ctr-row" :class="{ 'ctr-row--muted': node.muted }" :style="{ paddingLeft: `${depth * 16 + 8}px` }">
      <button
        v-if="node.children.length > 0"
        class="ctr-chevron"
        :class="{ 'ctr-chevron--open': expanded }"
        @click="emit('toggle-expand', node.key)"
      >
        <i class="fas fa-chevron-right"></i>
      </button>
      <span v-else class="ctr-chevron ctr-chevron--placeholder"></span>

      <label v-if="manageable && !readonly && node.children.length > 0" class="ctr-check" @click.stop>
        <input
          type="checkbox"
          class="ctr-checkbox"
          :checked="state === 'checked'"
          :indeterminate="state === 'indeterminate'"
          @change="emit('toggle-node', node)"
        />
      </label>

      <span class="ctr-icon" :class="iconClass"><i :class="iconName"></i></span>
      <span class="ctr-name" :title="node.name">{{ node.name }}</span>
      <span v-if="node.children.length > 0" class="ctr-count">{{ node.count }} 条</span>
      <button
        v-if="manageable && !readonly && node.children.length > 0"
        class="ctr-btn ctr-btn-danger"
        @click="emit('remove-group', node)"
      >
        <i class="fas fa-trash"></i> 移除该组
      </button>
    </div>

    <!-- 叶条目：仅在「最深分组节点」渲染（用例视图 result_type 下还有任务层，
         叶由任务层呈现；与挑选树 INT-1110 同口径，避免同一条目出现两个复选框） -->
    <div v-if="node.level !== 'case' && node.children.length === 0">
      <template v-for="id in node.itemIds" :key="id">
        <!-- INT-1833 组成区只读叶行（规范 18 §4.5）：源结果 #id + 用例名 + 设备/API 名 +
             result_type 徽章 + 执行/评估徽章 + 源结果时间（§11-8 未落地不渲染）+ 溯源 -->
        <div
          v-if="compositionMeta?.has(id)"
          class="ctr-leaf ctr-leaf--composition"
          :class="{ 'ctr-leaf--missing': compositionMeta.get(id)?.missing }"
          :style="{ paddingLeft: `${(depth + 1) * 16 + 8}px` }"
        >
          <span class="ctr-leaf-result">源结果 #{{ compositionMeta.get(id)?.resultId ?? id }}</span>
          <span class="ctr-leaf-case" :title="compositionMeta.get(id)?.sourceCaseName ?? ''">
            {{ compositionMeta.get(id)?.sourceCaseName || '未知用例' }}
          </span>
          <span v-if="compositionDeviceLabel(id)" class="ctr-leaf-dim">{{ compositionDeviceLabel(id) }}</span>
          <span class="ctr-leaf-rt">{{ compositionMeta.get(id)?.resultType || '结果类型待补充' }}</span>
          <span
            v-if="compositionMeta.get(id)?.executionStatus"
            class="ctr-leaf-status"
            :class="compositionMeta.get(id)?.executionStatus ?? ''"
          >{{ compositionStatusText(compositionMeta.get(id)?.executionStatus) }}</span>
          <span
            v-if="compositionMeta.get(id)?.evaluated !== null && compositionMeta.get(id)?.evaluated !== undefined"
            class="ctr-leaf-eval"
            :class="{ 'ctr-leaf-eval--done': compositionMeta.get(id)?.evaluated }"
          >{{ compositionMeta.get(id)?.evaluated ? '已评估' : '未评估' }}</span>
          <span v-if="compositionMeta.get(id)?.missing" class="ctr-leaf-invalid">
            <i class="fas fa-triangle-exclamation"></i> 已失效
          </span>
          <!-- 源结果时间：仅 §11-8 的 result_created_at 有值时渲染（不占位、不显示「—」） -->
          <span
            v-if="compositionMeta.get(id)?.resultCreatedAt"
            class="ctr-leaf-time"
            title="源结果时间"
          >{{ formatCompositionTime(compositionMeta.get(id)?.resultCreatedAt) }}</span>
          <!-- 原生 button 会被全局 button 基线改写样式，用 div[role=button] 承载文本钮 -->
          <div
            role="button"
            tabindex="0"
            class="ctr-trace"
            title="打开来源任务详情"
            @click.stop="emit('trace', id)"
            @keydown.enter.prevent="emit('trace', id)"
            @keydown.space.prevent="emit('trace', id)"
          >溯源</div>
        </div>

        <div
          v-else
          class="ctr-leaf"
          :class="{ invalid: leafMeta.get(id)?.invalid }"
          :style="{ paddingLeft: `${(depth + 1) * 16 + 8}px` }"
        >
          <label v-if="manageable && !readonly" class="ctr-check" @click.stop>
            <input
              type="checkbox"
              class="ctr-checkbox"
              :checked="selected.has(id)"
              @change="emit('toggle-leaf', id)"
            />
          </label>
          <span class="ctr-leaf-case">{{ leafMeta.get(id)?.sourceCaseName || leafMeta.get(id)?.sourceCaseId || '#' + (leafMeta.get(id)?.resultId ?? id) }}</span>
          <span class="ctr-leaf-dim">
            {{ leafMeta.get(id)?.sourceDeviceId != null
              ? (leafMeta.get(id)?.sourceDeviceName || `设备 ${leafMeta.get(id)?.sourceDeviceId}`)
              : (leafMeta.get(id)?.sourceApiId != null ? `API ${leafMeta.get(id)?.sourceApiId}` : '-') }}
          </span>
          <span v-if="leafMeta.get(id)?.sourceResultType" class="ctr-leaf-rt">{{ leafMeta.get(id)?.sourceResultType }}</span>
          <span class="ctr-leaf-status" :class="leafMeta.get(id)?.executionStatus">{{ statusText(leafMeta.get(id)?.executionStatus) }}</span>
          <span v-if="leafMeta.get(id)?.invalid" class="ctr-leaf-invalid"><i class="fas fa-triangle-exclamation"></i> 已失效（源结果已删除）</span>
          <button v-if="manageable && !readonly" class="ctr-btn ctr-btn-sm" @click="emit('remove-leaf', id)"><i class="fas fa-times"></i> 移除</button>
        </div>
      </template>
    </div>

    <div v-if="expanded && node.children.length > 0 && node.level !== 'case'">
      <CartTreeNodeRow
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :selected="selected"
        :expanded-keys="expandedKeys"
        :leaf-meta="leafMeta"
        :manageable="manageable"
        :readonly="readonly"
        :composition-meta="compositionMeta"
        :depth="depth + 1"
        @toggle-node="(n) => emit('toggle-node', n)"
        @toggle-expand="(k) => emit('toggle-expand', k)"
        @toggle-leaf="(id) => emit('toggle-leaf', id)"
        @remove-leaf="(id) => emit('remove-leaf', id)"
        @remove-group="(n) => emit('remove-group', n)"
        @trace="(id) => emit('trace', id)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

/**
 * CartTreeNodeRow —— 购物车树节点行（递归组件）。
 * 节点三态由 cartTree.cartNodeState 派生；叶条目展示用例/设备/结果类型/状态/失效标记。
 * INT-1833：组成区只读（readonly，无复选框 / 移除钮）且叶行走组成口径
 * （compositionMeta 存在即启用：源结果 #id / 评估徽章 / 源结果时间 / 溯源）。
 */
import { computed } from 'vue';
import { cartNodeState, type CartTreeNode, type CartNodeCheckState } from './cartTree';
import type { PickCartItem } from '../../../infrastructure/api/cherryPickApi';
import type { CompositionEntry } from '../../../domain/model/containerComposition';
import {
  compositionStatusText,
  formatCompositionTime,
} from './compositionTree';
import PickCaseCard from '../../common/test-case/PickCaseCard.vue';

const props = withDefaults(defineProps<{
  node: CartTreeNode;
  selected: ReadonlySet<number>;
  expandedKeys: ReadonlySet<string>;
  leafMeta?: Map<number, PickCartItem>;
  manageable?: boolean;
  /** 只读（组成区）：隐藏三态复选框与移除钮，保留展开 / 收起 */
  readonly?: boolean;
  /** 组成条目元数据（提供时叶行按组成口径渲染） */
  compositionMeta?: ReadonlyMap<number, CompositionEntry>;
  depth: number;
}>(), {
  leafMeta: () => new Map<number, PickCartItem>(),
  manageable: false,
  readonly: false,
});

const emit = defineEmits<{
  (e: 'toggle-node', node: CartTreeNode): void;
  (e: 'toggle-expand', key: string): void;
  (e: 'toggle-leaf', itemId: number): void;
  (e: 'remove-leaf', itemId: number): void;
  (e: 'remove-group', node: CartTreeNode): void;
  (e: 'trace', resultId: number): void;
}>();

defineOptions({ name: 'CartTreeNodeRow' });

const state = computed<CartNodeCheckState>(() => cartNodeState(props.node, props.selected));
const expanded = computed(() => props.expandedKeys.has(props.node.key));

const iconClass = computed(() => ({
  'ctr-icon--task': props.node.level === 'task',
  'ctr-icon--case': props.node.level === 'case',
  'ctr-icon--device': props.node.level === 'device' && props.node.kind === 'device',
  'ctr-icon--api': props.node.level === 'device' && props.node.kind === 'api',
  'ctr-icon--rt': props.node.level === 'resultType',
  'ctr-icon--org': props.node.level === 'org',
  'ctr-icon--org-sub': props.node.level === 'orgSub',
}));
const iconName = computed(() => {
  switch (props.node.level) {
    case 'task': return 'fas fa-tasks';
    case 'case': return 'fas fa-list-check';
    case 'device': return props.node.kind === 'api' ? 'fas fa-arrow-right-arrow-left' : 'fas fa-mobile-screen';
    case 'resultType': return 'fas fa-tag';
    // 用例层组织：分组视图 = 文件夹，标签视图 = 标签；交叉子组用打开态图标区分层级
    case 'org': return props.node.org === 'tag' ? 'fas fa-tags' : 'fas fa-folder';
    case 'orgSub': return props.node.org === 'tag' ? 'fas fa-tag' : 'fas fa-folder-open';
    default: return 'fas fa-dot-circle';
  }
});

function statusText(status?: string | null): string {
  switch (status) {
    case 'completed': return '执行完成';
    case 'failed': return '执行失败';
    case 'stopped': return '已停止';
    case 'running': return '执行中';
    case 'pending': return '待执行';
    default: return status || '-';
  }
}

/** 组成叶行设备 / API 名（缺名容错显示 ID；两者都无 → 不渲染该位） */
function compositionDeviceLabel(id: number): string {
  const entry = props.compositionMeta?.get(id);
  if (!entry) return '';
  if (entry.sourceDeviceId !== null) {
    return entry.sourceDeviceName || `设备 ${entry.sourceDeviceId}`;
  }
  if (entry.sourceApiId !== null) {
    return entry.sourceApiName || `API ${entry.sourceApiId}`;
  }
  return '';
}
</script>

<style scoped>
.ctr-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-md);
}
.ctr-row:hover {
  background: var(--muted, #f8fafc);
}
.ctr-chevron {
  width: 16px;
  height: 16px;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--color-slate-400, #94a3b8);
  transition: transform 0.15s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ctr-chevron--open { transform: rotate(90deg); }
.ctr-chevron--placeholder { visibility: hidden; }
.ctr-check { display: inline-flex; align-items: center; flex-shrink: 0; }
.ctr-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary, #ff6a00);
}
.ctr-icon { width: 18px; color: var(--color-slate-400, #94a3b8); flex-shrink: 0; font-size: 13px; }
.ctr-icon--task { color: var(--primary, #ff6a00); }
.ctr-icon--case { color: var(--color-blue-500); }
.ctr-icon--device { color: var(--color-emerald-500); }
.ctr-icon--api { color: var(--color-violet-500); }
.ctr-icon--rt { color: var(--color-amber-500); }
/* INT-1831 用例层组织节点（分组视图 / 标签视图 + 交叉子组） */
.ctr-icon--org { color: var(--color-slate-500, #64748b); }
.ctr-icon--org-sub { color: var(--color-slate-400, #94a3b8); }
.ctr-row--muted .ctr-name { color: var(--color-slate-400, #94a3b8); }
.ctr-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--foreground, #1e293b);
}
.ctr-count {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: var(--muted, #f1f5f9);
  color: var(--muted-foreground, #64748b);
  font-size: 11px;
  font-weight: 500;
}
.ctr-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-md);
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  color: var(--foreground, #1e293b);
}
.ctr-btn:hover { border-color: var(--primary, #ff6a00); color: var(--primary, #ff6a00); }
.ctr-btn-sm { font-size: 12px; }
.ctr-btn-danger { border-color: var(--destructive, #dc2626); color: var(--destructive, #dc2626); }
.ctr-btn-danger:hover { background: var(--color-red-100); }
.ctr-leaf {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  font-size: 12px;
}
.ctr-leaf.invalid { background: var(--color-red-50); }
.ctr-leaf:hover { background: var(--color-slate-50, #f8fafc); }
.ctr-leaf-case { color: var(--foreground, #1e293b); min-width: 80px; }
.ctr-leaf-dim { color: var(--muted-foreground, #64748b); min-width: 70px; }
.ctr-leaf-rt {
  padding: 0 6px;
  border-radius: var(--radius-sm);
  background: var(--color-amber-50, #fffbeb);
  color: var(--color-amber-700);
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}
/* P3（UX 审计）：状态徽章改走 tokens 与 TaskCard exec-status-badge 同源，去硬编码 hex */
.ctr-leaf-status {
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 11px;
}
.ctr-leaf-status.completed { background: var(--color-emerald-100); color: var(--color-emerald-600); }
.ctr-leaf-status.failed { background: var(--color-red-100); color: var(--color-red-600); }
.ctr-leaf-status.stopped { background: var(--color-gray-100); color: var(--color-gray-500); }
.ctr-leaf-invalid { color: var(--destructive, #dc2626); font-size: 11px; }
/* INT-1110：购物车用例节点统一用例卡 compact（§4.2/§3.8.4） */
.ctr-case-card {
  margin: 2px 0;
}
/* INT-1833 深色可读：TestCaseCard 表面用常量 --color-white（共享样式文件，不在本卡范围），
   深色下白底 + 浅色文字读不清 → 组成区 / 购物车树内局部改语义令牌兜底。
   （PickCaseCard 把 ctr-case-card 合并到用例卡根元素上，故用同级复合选择器） */
.ctr-case-card.case-card {
  background-color: var(--card);
  color: var(--card-foreground);
}

/* ===== INT-1833 组成区只读叶行（规范 18 §4.5；全部取语义令牌，深浅同一套） ===== */
.ctr-leaf--composition {
  flex-wrap: wrap;
  color: var(--muted-foreground);
  border-radius: var(--radius-control);
}
.ctr-leaf--composition:hover {
  background: var(--muted);
}
.ctr-leaf-result {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  color: var(--muted-foreground);
}
.ctr-leaf--composition .ctr-leaf-case {
  color: var(--foreground);
  font-size: 12px;
  min-width: 0;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ctr-leaf--composition .ctr-leaf-dim {
  min-width: 0;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ctr-leaf--composition .ctr-leaf-rt {
  background: var(--muted);
  color: var(--muted-foreground);
  border-radius: var(--radius-tag);
}
.ctr-leaf--composition .ctr-leaf-status.completed {
  background: color-mix(in srgb, var(--success) 16%, transparent);
  color: var(--success);
}
.ctr-leaf--composition .ctr-leaf-status.failed {
  background: color-mix(in srgb, var(--destructive) 16%, transparent);
  color: var(--destructive);
}
.ctr-leaf--composition .ctr-leaf-status.stopped {
  background: var(--muted);
  color: var(--muted-foreground);
}
.ctr-leaf-eval {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  font-size: 11px;
  color: var(--muted-foreground);
}
.ctr-leaf-eval--done {
  border-color: var(--secondary);
  background: var(--secondary-light);
  color: var(--secondary);
}
.ctr-leaf-time {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  color: var(--muted-foreground);
  white-space: nowrap;
}
/* 失效叶行：弱化 + 删除线（深色下降透明读不清，规范 18 §10.4） */
.ctr-leaf--missing {
  color: var(--muted-foreground);
}
.ctr-leaf--missing .ctr-leaf-case,
.ctr-leaf--missing .ctr-leaf-result,
.ctr-leaf--missing .ctr-leaf-dim {
  text-decoration: line-through;
  color: var(--muted-foreground);
}
.ctr-trace {
  flex-shrink: 0;
  margin-left: auto;
  padding: 1px 4px;
  border-radius: var(--radius-tag);
  color: var(--secondary);
  font-size: 11px;
  cursor: pointer;
}
.ctr-trace:hover {
  text-decoration: underline;
}
.ctr-trace:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 1px;
}
</style>
