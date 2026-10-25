<template>
  <div ref="rootEl" class="cvs" role="tablist" :aria-label="ariaLabel" @keydown="onKeydown">
    <button
      v-for="item in VIEWS"
      :key="item.key"
      type="button"
      role="tab"
      class="cvs-btn"
      data-layout-btn
      :class="{ active: view === item.key }"
      :aria-selected="view === item.key ? 'true' : 'false'"
      :tabindex="view === item.key ? 0 : -1"
      @click="select(item.key)"
    >
      <i :class="item.icon"></i> {{ item.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * ContainerViewSwitcher —— 四视图切换器（INT-1833 · 规范 18 §3.2/§10.5）。
 * 任务视图（默认）｜用例视图｜设备视图｜结果类型视图；组成区与购物车 / 复核共用同一套视图枚举。
 *
 * 无障碍：role=tablist / tab + aria-selected，左右方向键切换（§10.5）。
 * 按钮带 `data-layout-btn` 退出 legacy button.css catch-all（该规则配色/背景优先级更高，
 * 会把「当前视图」高亮压平——同 NotificationPopover 分段控件口径）。
 * 购物车侧 `CartViewSwitcher` 直接复用本组件，视图项只有一份定义。
 */
import { ref } from 'vue';
import type { CartViewMode } from './cartTree';

const VIEWS: Array<{ key: CartViewMode; label: string; icon: string }> = [
  { key: 'task', label: '任务视图', icon: 'fas fa-clipboard-list' },
  { key: 'case', label: '用例视图', icon: 'fas fa-list-check' },
  { key: 'device', label: '设备视图', icon: 'fas fa-mobile-screen' },
  { key: 'resultType', label: '结果类型视图', icon: 'fas fa-tag' },
];

const props = withDefaults(defineProps<{
  /** 当前视图（任务视图为默认） */
  view: CartViewMode;
  /** tablist 无障碍名称 */
  ariaLabel?: string;
}>(), {
  ariaLabel: '视图切换',
});

const emit = defineEmits<{
  (e: 'update:view', view: CartViewMode): void;
}>();

defineOptions({ name: 'ContainerViewSwitcher' });

const rootEl = ref<HTMLElement | null>(null);

function select(view: CartViewMode) {
  if (view !== props.view) emit('update:view', view);
}

/** 左右方向键在四个视图间循环切换（§10.5），焦点跟随选中项（不依赖 DOM id，避免同页多切换器冲突） */
function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
  event.preventDefault();
  const index = VIEWS.findIndex((v) => v.key === props.view);
  const step = event.key === 'ArrowRight' ? 1 : -1;
  const nextIndex = (index + step + VIEWS.length) % VIEWS.length;
  emit('update:view', VIEWS[nextIndex].key);
  const tabs = rootEl.value?.querySelectorAll<HTMLElement>('[role="tab"]');
  tabs?.[nextIndex]?.focus();
}
</script>

<style scoped>
.cvs {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-control);
  background: var(--muted);
}
.cvs-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--muted-foreground);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cvs-btn:hover {
  color: var(--primary);
}
.cvs-btn.active {
  border-color: var(--border);
  background: var(--card);
  color: var(--primary);
  font-weight: 600;
}
.cvs-btn:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 1px;
}
</style>
