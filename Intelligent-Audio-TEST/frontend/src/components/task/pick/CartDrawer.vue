<template>
  <Teleport to="body">
    <div v-if="visible" class="cd-overlay" @click.self="emit('close')">
      <div class="cd-drawer">
        <!-- 头部 -->
        <div class="cd-header">
          <h3><i class="fas fa-cart-shopping"></i> 我的购物车</h3>
          <button class="cd-close" @click="emit('close')"><i class="fas fa-times"></i></button>
        </div>

        <!-- 工具栏（§8：algo_engineer 只读，增删钮隐藏） -->
        <div class="cd-toolbar">
          <span class="cd-toolbar-info">共 {{ cartCount }} 条（{{ invalidCount }} 条失效）</span>
          <template v-if="canWrite">
            <button v-if="selectedItemIds.size > 0" class="cd-btn cd-btn-danger" @click="removeSelectedItems">
              <i class="fas fa-trash"></i> 移除已选（{{ selectedItemIds.size }}）
            </button>
            <button v-if="invalidCount > 0" class="cd-btn" @click="removeInvalid">
              <i class="fas fa-trash-alt"></i> 移除失效条目（{{ invalidCount }}）
            </button>
            <button class="cd-btn" @click="clearAllCart"><i class="fas fa-trash"></i> 清空购物车</button>
            <button class="cd-btn" @click="openSaveSet"><i class="fas fa-save"></i> 另存为挑选集</button>
          </template>
        </div>

        <!-- 购物车树（任务→用例→设备→result_type 分组；manageable 随 RBAC） -->
        <div v-if="cartLoading" class="cd-empty"><i class="fas fa-spinner fa-spin"></i> 正在加载购物车…</div>
        <div v-else-if="cartCount === 0" class="cd-empty">
          <i class="fas fa-shopping-cart"></i>
          <p>购物车为空</p>
          <p class="cd-empty-hint">在任务详情或挑选合并页勾选执行结果，加入购物车后复核合并</p>
        </div>
        <div v-else class="cd-tree">
          <CartTree
            :roots="cartTreeRoots"
            :selected="selectedItemIds"
            :expanded-keys="cartExpandedKeys"
            :leaf-meta="cartLeafMeta"
            :manageable="canWrite"
            @toggle-node="onToggleCartNode"
            @toggle-expand="onToggleCartExpand"
            @toggle-leaf="toggleCartItem"
            @remove-leaf="onRemoveCartLeaf"
            @remove-group="onRemoveCartGroupNode"
          />
        </div>

        <!-- 挑选集 -->
        <div class="cd-sets" v-if="sets.length > 0">
          <h4><i class="fas fa-layer-group"></i> 我的挑选集</h4>
          <div v-for="s in sets" :key="s.setId" class="cd-set-row">
            <span class="cd-set-name">{{ s.name }}</span>
            <span class="cd-count">{{ s.itemCount }} 条</span>
            <template v-if="canWrite">
              <button class="cd-btn cd-btn-sm" @click="restoreSet(s.setId)"><i class="fas fa-undo"></i> 恢复进购物车</button>
              <button class="cd-btn cd-btn-sm" @click="onRemoveSet(s.setId)"><i class="fas fa-trash-alt"></i></button>
            </template>
          </div>
        </div>

        <!-- 底部 -->
        <div class="cd-footer">
          <button class="cd-btn" @click="emit('close')"><i class="fas fa-arrow-left"></i> 继续挑选</button>
          <span class="cd-spacer"></span>
          <button v-if="canWrite" class="cd-btn cd-btn-primary" :disabled="cartCount === 0" @click="emit('go-review')">
            <i class="fas fa-clipboard-check"></i> 去复核（{{ cartCount }}）
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * CartDrawer —— 全局购物车抽屉（INT-577 §4.4；导航栏角标入口，任意页面可达）。
 *
 * 购物车树（任务分组）+ 移除矩阵（单条/整组/批量/失效/清空）+ 另存挑选集；
 * 数据源 = usePickCart 单例镜像（与挑选页/复核同源，§6.3 非双源）。
 */
import { ref, computed } from 'vue';
import { usePickCart } from '../../../composables/task/usePickCart';
import { useNotification } from '../../../composables/modal/useNotification';
import { useModalControl } from '../../../composables/modal/useModal';
import { MODAL_TYPES } from '../../../composables/modal/constants';
import { useAuthStore } from '../../../store/authStore';
import { PermissionPoint } from '../../../domain/enums';
import CartTree from './CartTree.vue';
import { buildCartTree, toggleCartNode, type CartTreeNode } from './cartTree';
import type { PickCartItem } from '../../../infrastructure/api/cherryPickApi';

const props = defineProps<{
  visible: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'go-review'): void;
}>();

const notification = useNotification();
const modalControl = useModalControl();
const { hasPermission: can } = useAuthStore();
/** §8：增删/另存/复核整链 task:cherry_pick；algo_engineer（仅 task:read）只读可见 */
const canWrite = computed(() => can(PermissionPoint.TASK_CHERRY_PICK));
const {
  cart, cartLoading, cartCount, invalidCount, sets,
  refreshCart, removeItem, removeItems, clearCart,
  saveAsSet, restoreSetToCart, deleteSet,
} = usePickCart();

const selectedItemIds = ref<Set<number>>(new Set());

/** 购物车树（§4.2 任务→用例→设备/API→result_type 分组，与挑选页同构） */
const cartTreeRoots = computed(() => buildCartTree(cart.value.groups));
const cartLeafMeta = computed(() => {
  const m = new Map<number, PickCartItem>();
  for (const g of cart.value.groups) {
    for (const it of g.items) m.set(it.itemId, it);
  }
  return m;
});
const cartExpandedKeys = ref<Set<string>>(new Set());

function toggleCartItem(itemId: number) {
  const next = new Set(selectedItemIds.value);
  if (next.has(itemId)) next.delete(itemId); else next.add(itemId);
  selectedItemIds.value = next;
}

function onToggleCartNode(node: CartTreeNode) {
  selectedItemIds.value = toggleCartNode(node, selectedItemIds.value);
}

function onToggleCartExpand(key: string) {
  const next = new Set(cartExpandedKeys.value);
  if (next.has(key)) next.delete(key); else next.add(key);
  cartExpandedKeys.value = next;
}

function onRemoveCartLeaf(itemId: number) {
  removeOne(itemId);
}

/** 节点「移除该组」（任务/用例/设备/结果类型；将移除该节点下全部条目） */
async function onRemoveCartGroupNode(node: CartTreeNode) {
  const label = node.level === 'task' ? '来源任务' : node.level === 'case' ? '用例' : node.level === 'device' ? (node.kind === 'api' ? 'API' : '设备') : '结果类型';
  let confirmed = false;
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '移除该组',
      content: `将移除该${label}「${node.name}」下的 ${node.count} 条结果，是否继续？`,
      confirmText: '移除',
      cancelText: '取消',
    });
  } catch {
    return;
  }
  if (!confirmed) return;
  try {
    await removeItems([...node.itemIds]);
    const next = new Set(selectedItemIds.value);
    for (const id of node.itemIds) next.delete(id);
    selectedItemIds.value = next;
    notification.success(`已移除 ${node.count} 条`);
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

async function removeOne(itemId: number) {
  try {
    await removeItem(itemId);
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

async function removeSelectedItems() {
  try {
    await removeItems([...selectedItemIds.value]);
    selectedItemIds.value = new Set();
    notification.success('已移除');
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

async function removeInvalid() {
  if (cart.value.invalidItemIds.length === 0) return;
  try {
    await removeItems(cart.value.invalidItemIds);
    notification.success('失效条目已移除');
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

async function clearAllCart() {
  let confirmed = false;
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '清空购物车',
      content: `将清空购物车全部 ${cartCount.value} 条结果，是否继续？`,
      confirmText: '清空',
      cancelText: '取消',
    });
  } catch {
    return;
  }
  if (!confirmed) return;
  try {
    await clearCart();
    notification.success('购物车已清空');
  } catch (error: any) {
    notification.error(error?.message || '清空失败');
  }
}

async function openSaveSet() {
  let name = '';
  try {
    const result = await modalControl.open(MODAL_TYPES.INPUT_CONFIRM, {
      title: '另存挑选集',
      label: '挑选集名称',
      initialValue: `挑选集_${new Date().toISOString().slice(0, 10)}`,
      hint: '同名允许重复保存',
      confirmText: '保存',
    });
    name = String(result?.value ?? '').trim();
  } catch {
    return;
  }
  if (!name) return;
  try {
    const outcome = await saveAsSet(name);
    notification.success(`挑选集「${outcome.name}」已保存（${outcome.itemCount} 条）`);
  } catch (error: any) {
    notification.error(error?.message || '另存挑选集失败');
  }
}

async function onRemoveSet(setId: number) {
  try {
    await deleteSet(setId);
  } catch (error: any) {
    notification.error(error?.message || '删除挑选集失败');
  }
}

async function restoreSet(setId: number) {
  try {
    const outcome = await restoreSetToCart(setId);
    notification.success(`已恢复 ${outcome.added?.length ?? 0} 条进购物车`);
  } catch (error: any) {
    notification.error(error?.message || '挑选集恢复失败');
  }
}
</script>

<style scoped>
.cd-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgb(0 0 0 / 0.4);
  display: flex;
  justify-content: flex-end;
}
.cd-drawer {
  width: min(480px, 92vw);
  height: 100%;
  background: #fff;
  box-shadow: -4px 0 24px rgb(0 0 0 / 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.cd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-slate-200, #e2e8f0);
}
.cd-header h3 {
  font-size: 16px;
  margin: 0;
  color: var(--foreground, #1e293b);
}
.cd-close {
  border: none;
  background: none;
  font-size: 16px;
  color: var(--color-slate-400, #94a3b8);
  cursor: pointer;
}
.cd-close:hover { color: var(--foreground, #1e293b); }
.cd-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-slate-100, #f1f5f9);
}
.cd-toolbar-info {
  flex: 1;
  font-size: 13px;
  color: var(--color-slate-500, #64748b);
}
.cd-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--border-radius-md);
  background: #fff;
  font-size: 13px;
  cursor: pointer;
  color: var(--foreground, #1e293b);
  transition: all 0.15s ease;
}
.cd-btn:hover {
  border-color: var(--primary, #ff6a00);
  color: var(--primary, #ff6a00);
}
.cd-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.cd-btn-primary {
  background: var(--primary, #ff6a00);
  border-color: var(--primary, #ff6a00);
  color: #fff;
}
.cd-btn-primary:hover {
  background: var(--primary-dark, #e55d00);
  color: #fff;
}
.cd-btn-danger {
  border-color: var(--danger-color, #dc2626);
  color: var(--danger-color, #dc2626);
}
.cd-btn-danger:hover { background: #fee2e2; }
.cd-btn-sm { padding: 3px 8px; font-size: 12px; }
.cd-groups {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cd-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--color-slate-400, #94a3b8);
  text-align: center;
  padding: 24px;
}
.cd-empty i { font-size: 36px; color: var(--color-slate-300, #cbd5e1); margin-bottom: 8px; }
.cd-empty-hint { font-size: 12px !important; color: var(--color-slate-400, #94a3b8); }
.cd-group {
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--border-radius-md);
  overflow: hidden;
}
.cd-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--color-slate-50, #f8fafc);
  border-bottom: 1px solid var(--color-slate-200, #e2e8f0);
}
.cd-group-icon { color: var(--primary, #ff6a00); font-size: 13px; }
.cd-group-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}
.cd-count {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--border-radius-full);
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-500, #64748b);
  font-size: 11px;
  font-weight: 500;
}
.cd-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
}
.cd-row.invalid { background: #fef2f2; }
.cd-row:hover { background: var(--color-slate-50, #f8fafc); }
.cd-check { display: inline-flex; align-items: center; }
.cd-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary, #ff6a00);
}
.cd-row-case { color: var(--foreground, #1e293b); min-width: 80px; }
.cd-row-dim { color: var(--color-slate-500, #64748b); min-width: 70px; }
.cd-row-rt {
  padding: 0 6px;
  border-radius: var(--border-radius-sm);
  background: var(--color-amber-50, #fffbeb);
  color: #b45309;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}
.cd-row-invalid { color: var(--danger-color, #dc2626); font-size: 11px; }
.cd-sets {
  padding: 12px 16px;
  border-top: 1px solid var(--color-slate-100, #f1f5f9);
  max-height: 180px;
  overflow-y: auto;
}
.cd-sets h4 { font-size: 13px; color: var(--color-slate-600, #475569); margin-bottom: 8px; }
.cd-set-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 13px;
}
.cd-set-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cd-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--color-slate-200, #e2e8f0);
}
.cd-spacer { flex: 1; }
</style>
