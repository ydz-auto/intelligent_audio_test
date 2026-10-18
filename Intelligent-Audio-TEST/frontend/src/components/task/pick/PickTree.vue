<template>
  <div class="pick-tree">
    <div v-if="roots.length === 0" class="pick-tree-empty">
      <i class="fas fa-inbox"></i>
      <p>无符合条件的执行结果</p>
      <p class="pick-tree-empty-hint">仅已完成、执行失败、已停止的终态任务可挑选，默认剔除已删除用例的结果</p>
    </div>
    <PickTreeNodeRow
      v-for="node in roots"
      :key="node.key"
      :node="node"
      :selected="selected"
      :expanded-keys="expandedKeys"
      :already-added="alreadyAdded ?? EMPTY_SET"
      :leaf-meta="leafMeta ?? EMPTY_MAP"
      :depth="0"
      @toggle-node="(n) => emit('toggle-node', n)"
      @toggle-expand="(k) => emit('toggle-expand', k)"
      @toggle-leaf="(rid) => emit('toggle-leaf', rid)"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * PickTree —— 多级挑选树（INT-577 §3，挑选页/购物车共用）。
 *
 * 四级分组（任务→用例→设备/API→result_type）+ 结果行叶；节点三态派生自
 * selectedResultIds（唯一真相），联动规则 R1-R10 由 pickTree.ts 纯逻辑承载。
 * 默认收起至任务级（根节点收起，count Badge 常显）。
 */
import PickTreeNodeRow from './PickTreeNodeRow.vue';
import type { PickTreeNode } from './pickTree';
import type { PickCandidate } from '../../../infrastructure/api/cherryPickApi';

const EMPTY_SET = new Set<number>();
const EMPTY_MAP = new Map<number, PickCandidate>();

const props = defineProps<{
  roots: PickTreeNode[];
  /** 选中叶 result_id 集（三态派生唯一真相） */
  selected: ReadonlySet<number>;
  /** 展开的节点 key 集 */
  expandedKeys: ReadonlySet<string>;
  /** R10：已在购物车的 result_id 集（叶行「已加购」标记） */
  alreadyAdded?: ReadonlySet<number>;
  /** 叶行元数据（result_id → 候选行，展示用例/设备/结果类型/状态） */
  leafMeta?: Map<number, PickCandidate>;
}>();

const emit = defineEmits<{
  (e: 'toggle-node', node: PickTreeNode): void;
  (e: 'toggle-expand', key: string): void;
  (e: 'toggle-leaf', resultId: number): void;
}>();

defineOptions({ name: 'PickTree' });
</script>

<style scoped>
.pick-tree-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--color-slate-400, #94a3b8);
}
.pick-tree-empty i {
  font-size: 36px;
  color: var(--color-slate-300, #cbd5e1);
  margin-bottom: 8px;
}
.pick-tree-empty p {
  margin: 4px 0;
  font-size: 13px;
}
.pick-tree-empty-hint {
  font-size: 12px !important;
  color: var(--color-slate-400, #94a3b8);
}
</style>
