<template>
  <div class="pco-controls">
    <button type="button" class="pco-btn" data-layout-btn :class="{ active: org === 'group' }" @click="setOrg('group')">
      <i class="fas fa-folder"></i> 分组视图
    </button>
    <button type="button" class="pco-btn" data-layout-btn :class="{ active: org === 'tag' }" @click="setOrg('tag')">
      <i class="fas fa-tags"></i> 标签视图
    </button>
    <span class="pco-controls-sep"></span>
    <button type="button" class="pco-btn" data-layout-btn :class="{ active: subView === 'flat' }" @click="setSubView('flat')">
      平铺
    </button>
    <button type="button" class="pco-btn" data-layout-btn :class="{ active: subView !== 'flat' }" @click="setSubView(crossValue)">
      {{ crossLabel }}
    </button>
    <span v-if="fallbackOnly && hint !== null" class="pco-hint">{{ hint || DEFAULT_HINT }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * PickCaseOrgControls —— 用例层组织控件（分组视图 / 标签视图 × 平铺 / 交叉）。
 * 挑选树（PickCaseOrgList）与购物车四视图（INT-1831）共用同一套控件与口径；
 * 组织只影响用例层视觉分组，勾选联动与共享选中集不变（会话态由调用方持有）。
 * 按钮带 `data-layout-btn` 退出 legacy button.css catch-all——否则全局 button 规则
 * 压掉 scoped 的选中态配色/背景，分组视图 / 标签视图看不出当前维度
 * （同 NotificationPopover 分段控件口径）。
 */
import { computed } from 'vue';

const DEFAULT_HINT = '候选未返分组/标签字段，按「未分组」/「未设置标签」组织（§11-7）';

const props = withDefaults(defineProps<{
  /** 组织维度（分组视图 / 标签视图） */
  org: 'group' | 'tag';
  /** 子视图（平铺 / 交叉：分组视图内按标签、标签视图内按用例分组） */
  subView: 'flat' | 'byTag' | 'byGroup';
  /** 全落单兜底桶（候选/条目无组织字段）时显示兜底提示 */
  fallbackOnly?: boolean;
  /**
   * 兜底提示文案覆盖（组成区显式传 null 表示组织字段有值时不再提示）。
   * 缺省（undefined）= 沿用默认提示；null = 不显示提示（§4.2 不得出现与事实相反的文案）。
   */
  hint?: string | null;
}>(), {
  fallbackOnly: false,
});

const emit = defineEmits<{
  (e: 'update:org', org: 'group' | 'tag'): void;
  (e: 'update:subView', subView: 'flat' | 'byTag' | 'byGroup'): void;
}>();

/** 交叉子视图当前维度（分组视图 → 按标签；标签视图 → 按用例分组） */
const crossValue = computed<'byTag' | 'byGroup'>(() => (props.org === 'group' ? 'byTag' : 'byGroup'));
const crossLabel = computed(() => (props.org === 'group' ? '按标签' : '按用例分组'));

/** 切换组织维度：会话态（切视图保持）；org 切换重置子视图为平铺（对齐 React PickCaseView） */
function setOrg(org: 'group' | 'tag') {
  emit('update:org', org);
  emit('update:subView', 'flat');
}
function setSubView(subView: 'flat' | 'byTag' | 'byGroup') {
  emit('update:subView', subView);
}
</script>

<style scoped>
.pco-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: var(--muted, #f8fafc);
  border-bottom: 1px solid var(--border, #e2e8f0);
}
.pco-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--border, #cbd5e1);
  border-radius: var(--radius-md);
  background: var(--card, #fff);
  color: var(--foreground, #1e293b);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.pco-btn:hover {
  border-color: var(--primary, #ff6a00);
  color: var(--primary, #ff6a00);
}
.pco-btn.active {
  border-color: var(--primary, #ff6a00);
  background: var(--accent, #fff7ed);
  color: var(--primary, #ff6a00);
}
.pco-controls-sep {
  width: 1px;
  height: 16px;
  background: var(--border, #e2e8f0);
  margin: 0 2px;
}
.pco-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted-foreground, #94a3b8);
}
</style>
