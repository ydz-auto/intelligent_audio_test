<template>
  <div class="cvs">
    <button
      v-for="item in VIEWS"
      :key="item.key"
      type="button"
      class="cvs-btn"
      data-layout-btn
      :class="{ active: view === item.key }"
      @click="emit('update:view', item.key)"
    >
      <i :class="item.icon"></i> {{ item.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * CartViewSwitcher —— 购物车 / 复核四视图切换器（INT-1831，UX设计规范-VUE 18 §3.2）。
 * 任务视图（默认）｜用例视图｜设备视图｜结果类型视图：四视图共享同一购物车条目集与
 * 选中 item_id 集（切换不丢勾选、不改提交载荷），与 React §4.2 `cart-view-switcher` 同口径。
 * 按钮带 `data-layout-btn` 退出 legacy button.css catch-all（该规则配色/背景优先级更高，
 * 会把「当前视图」高亮压平——同 NotificationPopover 分段控件口径）。
 */
import type { CartViewMode } from './cartTree';

const VIEWS: Array<{ key: CartViewMode; label: string; icon: string }> = [
  { key: 'task', label: '任务视图', icon: 'fas fa-clipboard-list' },
  { key: 'case', label: '用例视图', icon: 'fas fa-list-check' },
  { key: 'device', label: '设备视图', icon: 'fas fa-mobile-screen' },
  { key: 'resultType', label: '结果类型视图', icon: 'fas fa-tag' },
];

defineProps<{
  /** 当前视图（任务视图为默认） */
  view: CartViewMode;
}>();

const emit = defineEmits<{
  (e: 'update:view', view: CartViewMode): void;
}>();

defineOptions({ name: 'CartViewSwitcher' });
</script>

<style scoped>
.cvs {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-md);
  background: var(--muted, #f1f5f9);
}
.cvs-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground, #64748b);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cvs-btn:hover {
  color: var(--primary, #ff6a00);
}
.cvs-btn.active {
  border-color: var(--border, #e2e8f0);
  background: var(--card, #fff);
  color: var(--primary, #ff6a00);
  font-weight: 600;
}
</style>
