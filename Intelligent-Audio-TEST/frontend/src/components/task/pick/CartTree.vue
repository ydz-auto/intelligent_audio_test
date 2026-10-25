<template>
  <div class="ct">
    <div v-if="roots.length === 0" class="ct-empty">
      <i class="fas fa-shopping-cart"></i>
      <p>购物车为空</p>
    </div>
    <CartTreeNodeRow
      v-for="node in roots"
      :key="node.key"
      :node="node"
      :selected="selected"
      :expanded-keys="expandedKeys"
      :leaf-meta="leafMeta"
      :manageable="manageable"
      :depth="0"
      @toggle-node="(n) => emit('toggle-node', n)"
      @toggle-expand="(k) => emit('toggle-expand', k)"
      @toggle-leaf="(id) => emit('toggle-leaf', id)"
      @remove-leaf="(id) => emit('remove-leaf', id)"
      @remove-group="(n) => emit('remove-group', n)"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * CartTree —— 购物车 / 复核树（INT-577 §4.2，INT-1831 四视图基座；购物车抽屉/复核共用）。
 *
 * 层级由 cartTree.ts 的四视图 builder 产出（任务视图默认：任务 → 用例层组织 → 用例卡 →
 * 设备/API → result_type → 叶；用例 / 设备 / 结果类型视图任务层在叶前一级）；叶 = 购物车条目。
 * manageable=true 时展示移除钮（§4.3 移除矩阵：单条 X / 节点「移除该组」）；
 * 选中态用于批量移除（selectedItemIds 唯一真相，四视图共用、切换不丢，联动规则与挑选树 R1-R5 同构）。
 */
import CartTreeNodeRow from './CartTreeNodeRow.vue';
import type { CartTreeNode } from './cartTree';
import type { PickCartItem } from '../../../infrastructure/api/cherryPickApi';

const props = defineProps<{
  roots: CartTreeNode[];
  /** 选中叶 item_id 集（批量移除选择） */
  selected: ReadonlySet<number>;
  expandedKeys: ReadonlySet<string>;
  /** 叶元数据（item_id → 购物车条目） */
  leafMeta: Map<number, PickCartItem>;
  /** 是否可管理（移除钮显隐；algo_engineer 只读 false） */
  manageable?: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggle-node', node: CartTreeNode): void;
  (e: 'toggle-expand', key: string): void;
  (e: 'toggle-leaf', itemId: number): void;
  (e: 'remove-leaf', itemId: number): void;
  (e: 'remove-group', node: CartTreeNode): void;
}>();

defineOptions({ name: 'CartTree' });
</script>

<style scoped>
.ct-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--color-slate-400, #94a3b8);
}
.ct-empty i {
  font-size: 36px;
  color: var(--color-slate-300, #cbd5e1);
  margin-bottom: 8px;
}
.ct-empty p {
  margin: 4px 0;
  font-size: 13px;
}
</style>
