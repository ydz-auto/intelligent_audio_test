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
        class="ctr-case-card"
        @toggle="emit('toggle-node', node)"
        @toggle-open="emit('toggle-expand', node.key)"
      >
        <!-- §4.3 节点「移除该组」走统一卡行内操作插槽（INT-1103 PickCaseCard 口径） -->
        <template #actions>
          <button
            v-if="manageable"
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
            :depth="depth + 1"
            @toggle-node="(n) => emit('toggle-node', n)"
            @toggle-expand="(k) => emit('toggle-expand', k)"
            @toggle-leaf="(id) => emit('toggle-leaf', id)"
            @remove-leaf="(id) => emit('remove-leaf', id)"
            @remove-group="(n) => emit('remove-group', n)"
          />
        </template>
      </PickCaseCard>
    </template>

    <!-- 普通节点行（非用例节点） -->
    <div v-else class="ctr-row" :style="{ paddingLeft: `${depth * 16 + 8}px` }">
      <button
        v-if="node.children.length > 0"
        class="ctr-chevron"
        :class="{ 'ctr-chevron--open': expanded }"
        @click="emit('toggle-expand', node.key)"
      >
        <i class="fas fa-chevron-right"></i>
      </button>
      <span v-else class="ctr-chevron ctr-chevron--placeholder"></span>

      <label v-if="manageable && node.children.length > 0" class="ctr-check" @click.stop>
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
        v-if="manageable && node.children.length > 0"
        class="ctr-btn ctr-btn-danger"
        @click="emit('remove-group', node)"
      >
        <i class="fas fa-trash"></i> 移除该组
      </button>
    </div>

    <!-- 叶条目 -->
    <div v-if="node.level === 'resultType' || node.children.length === 0">
      <div
        v-for="id in node.itemIds"
        :key="id"
        class="ctr-leaf"
        :class="{ invalid: leafMeta.get(id)?.invalid }"
        :style="{ paddingLeft: `${(depth + 1) * 16 + 8}px` }"
      >
        <label v-if="manageable" class="ctr-check" @click.stop>
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
        <button v-if="manageable" class="ctr-btn ctr-btn-sm" @click="emit('remove-leaf', id)"><i class="fas fa-times"></i> 移除</button>
      </div>
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
        :depth="depth + 1"
        @toggle-node="(n) => emit('toggle-node', n)"
        @toggle-expand="(k) => emit('toggle-expand', k)"
        @toggle-leaf="(id) => emit('toggle-leaf', id)"
        @remove-leaf="(id) => emit('remove-leaf', id)"
        @remove-group="(n) => emit('remove-group', n)"
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
 */
import { computed } from 'vue';
import { cartNodeState, type CartTreeNode, type CartNodeCheckState } from './cartTree';
import type { PickCartItem } from '../../../infrastructure/api/cherryPickApi';
import PickCaseCard from '../../common/test-case/PickCaseCard.vue';

const props = defineProps<{
  node: CartTreeNode;
  selected: ReadonlySet<number>;
  expandedKeys: ReadonlySet<string>;
  leafMeta: Map<number, PickCartItem>;
  manageable: boolean;
  depth: number;
}>();

const emit = defineEmits<{
  (e: 'toggle-node', node: CartTreeNode): void;
  (e: 'toggle-expand', key: string): void;
  (e: 'toggle-leaf', itemId: number): void;
  (e: 'remove-leaf', itemId: number): void;
  (e: 'remove-group', node: CartTreeNode): void;
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
}));
const iconName = computed(() => {
  switch (props.node.level) {
    case 'task': return 'fas fa-tasks';
    case 'case': return 'fas fa-list-check';
    case 'device': return props.node.kind === 'api' ? 'fas fa-arrow-right-arrow-left' : 'fas fa-mobile-screen';
    case 'resultType': return 'fas fa-tag';
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
  background: var(--color-slate-50, #f8fafc);
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
.ctr-icon--case { color: #3b82f6; }
.ctr-icon--device { color: #10b981; }
.ctr-icon--api { color: #8b5cf6; }
.ctr-icon--rt { color: #f59e0b; }
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
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-500, #64748b);
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
.ctr-btn-danger:hover { background: #fee2e2; }
.ctr-leaf {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  font-size: 12px;
}
.ctr-leaf.invalid { background: #fef2f2; }
.ctr-leaf:hover { background: var(--color-slate-50, #f8fafc); }
.ctr-leaf-case { color: var(--foreground, #1e293b); min-width: 80px; }
.ctr-leaf-dim { color: var(--color-slate-500, #64748b); min-width: 70px; }
.ctr-leaf-rt {
  padding: 0 6px;
  border-radius: var(--radius-sm);
  background: var(--color-amber-50, #fffbeb);
  color: #b45309;
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

</style>
