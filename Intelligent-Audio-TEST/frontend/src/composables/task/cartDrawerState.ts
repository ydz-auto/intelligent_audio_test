// -*- coding: utf-8 -*-
/**
 * 全局购物车抽屉状态（INT-577 §6.3 同步点：购物车角标/抽屉跨组件共享）。
 *
 * 模块级单例 visible ref：App.vue 导航栏角标与 Tasks/CherryPickPanel 的
 * 「打开购物车」入口共享同一抽屉实例（非双源）；任意组件 open() 即可拉起。
 */
import { ref } from 'vue';

const visible = ref(false);

export function useCartDrawerState() {
  function open() {
    visible.value = true;
  }
  function close() {
    visible.value = false;
  }
  return { visible, open, close };
}
