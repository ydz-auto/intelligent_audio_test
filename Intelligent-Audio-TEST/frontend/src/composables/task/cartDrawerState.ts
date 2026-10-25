// -*- coding: utf-8 -*-
/**
 * 全局购物车抽屉状态（INT-577 §6.3 同步点：购物车角标/抽屉跨组件共享）。
 *
 * 模块级单例 visible ref：App.vue 导航栏角标与 Tasks/CherryPickPanel 的
 * 「打开购物车」入口共享同一抽屉实例（非双源）；任意组件 open() 即可拉起。
 *
 * layerHost（INT-1838 P2-1）：从模态窗内拉起抽屉时（挑选合并容器详情「复用本次结果重新挑选」），
 * 由调用方传入该模态的遮罩元素，抽屉 Teleport 进这个遮罩的层叠上下文里 —— 与 React 版把
 * CartDrawer 受控渲染在详情内同口径：抽屉盖在模态内容之上且可直接操作，而全局 toast、
 * 后开的模态仍按原层级工作（抽屉不抢占整页最高层）。缺省 null = 仍走 body 全局层。
 * dismissHost（INT-1838 P2-1 随附）：宿主模态的收起动作，抽屉「去复核」时先调用，
 * 避免复核向导开在详情模态之后而看不见。
 */
import { ref } from 'vue';

const visible = ref(false);
const layerHost = ref<HTMLElement | null>(null);
/** 宿主模态的收起动作（「去复核」前调用，否则向导开在详情模态之后） */
const layerDismiss = ref<(() => void) | null>(null);

export function useCartDrawerState() {
  function open(options?: { layerHost?: HTMLElement | null; dismissHost?: (() => void) | null }) {
    layerHost.value = options?.layerHost ?? null;
    layerDismiss.value = options?.dismissHost ?? null;
    visible.value = true;
  }
  function close() {
    visible.value = false;
    layerHost.value = null;
    layerDismiss.value = null;
  }
  /** 收起宿主模态（无宿主时为空操作）；不改抽屉可见性，由调用方决定 */
  function dismissHost() {
    const dismiss = layerDismiss.value;
    layerDismiss.value = null;
    dismiss?.();
  }
  return { visible, layerHost, open, close, dismissHost };
}
