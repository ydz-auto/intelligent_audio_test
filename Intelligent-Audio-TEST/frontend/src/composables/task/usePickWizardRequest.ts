// -*- coding: utf-8 -*-
/**
 * 挑选向导开启请求（INT-577 P0 修复）。
 *
 * 背景：布局壳 router-view 无 :key=fullPath 重挂载（AuthenticatedLayout.vue），
 * 批量「加入挑选」/「开始挑选」入口与 CherryPickPanel 分属不同页签——面板未挂载时
 * 无法直接打开向导。本模块以模块级单例承载「向导开启请求」（与 usePickCart
 * 同款单例模式）：发起方（Tasks.vue 批量「加入挑选」/「开始挑选」）写请求，
 * 并显式 switchTab('cherryPick') 让 CherryPickPanel 挂载，新面板经 immediate
 * watch 消费请求并自开向导；向导关闭/下单时清除，避免跨会话泄漏（§10 #5 会话级记忆口径）。
 */
import { ref } from 'vue';

export interface PickWizardRequest {
  /** 批量「加入挑选」任务级预选（R7 整任务加购，等价旧「合并任务」入口） */
  presetTaskIds?: (number | string)[];
  /** 直达步骤（购物车抽屉「去复核」→ review；缺省 pick） */
  step?: 'pick' | 'cart' | 'review' | 'checkout';
}

const pendingRequest = ref<PickWizardRequest | null>(null);

/** 发起向导开启请求（在导航/重挂载之前写入，跨实例存活） */
export function requestPickWizard(req: PickWizardRequest): void {
  pendingRequest.value = req;
}

/** 清除未消费的请求（向导关闭/下单/导航失败时调用，防泄漏） */
export function clearPickWizardRequest(): void {
  pendingRequest.value = null;
}

export function usePickWizardRequest() {
  return { pendingRequest, requestPickWizard, clearPickWizardRequest };
}
