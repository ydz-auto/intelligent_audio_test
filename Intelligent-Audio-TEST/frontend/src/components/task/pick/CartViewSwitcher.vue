<template>
  <ContainerViewSwitcher
    :view="view"
    aria-label="购物车视图切换"
    @update:view="(v) => emit('update:view', v)"
  />
</template>

<script setup lang="ts">
/**
 * CartViewSwitcher —— 购物车 / 复核四视图切换器（INT-1831，UX设计规范-VUE 18 §3.2）。
 * 任务视图（默认）｜用例视图｜设备视图｜结果类型视图：四视图共享同一购物车条目集与
 * 选中 item_id 集（切换不丢勾选、不改提交载荷），与 React §4.2 `cart-view-switcher` 同口径。
 *
 * INT-1833：视图项与无障碍（role=tablist + 方向键）收敛到 `ContainerViewSwitcher`，
 * 组成区与购物车共用一份定义，本组件只保留购物车语义的薄封装（调用方 API 不变）。
 */
import ContainerViewSwitcher from './ContainerViewSwitcher.vue';
import type { CartViewMode } from './cartTree';

defineProps<{
  /** 当前视图（任务视图为默认） */
  view: CartViewMode;
}>();

const emit = defineEmits<{
  (e: 'update:view', view: CartViewMode): void;
}>();

defineOptions({ name: 'CartViewSwitcher' });
</script>
