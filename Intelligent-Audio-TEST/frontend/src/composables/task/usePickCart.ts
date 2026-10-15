// -*- coding: utf-8 -*-
/**
 * 挑选购物车 composable（INT-339）。
 *
 * 全局单例状态（模块级 ref 闭包）：购物车按用户持久化在服务端，
 * 本状态为会话内镜像（角标计数/分组展示），加购/移除后同步刷新。
 * Application 层：只见 Domain（camelCase），API 访问收敛到 infrastructure/api。
 */
import { ref, computed } from 'vue';
import { cherryPickApi } from '../../infrastructure/api';
import type { PickCart, PickCartItem, PickCartGroup, PickSetSummary } from '../../infrastructure/api/cherryPickApi';

// 模块级单例状态（跨组件共享，对齐 useAuthStore 模式）
const cart = ref<PickCart>({ groups: [], total: 0, invalidItemIds: [] });
const cartLoading = ref(false);
const savingSet = ref(false);
const sets = ref<PickSetSummary[]>([]);

/** 购物车条目总数（全局角标计数） */
const cartCount = computed(() => cart.value.total);
/** 失效条目数（下单前校验提示，§10） */
const invalidCount = computed(() => cart.value.invalidItemIds.length);

async function refreshCart() {
  cartLoading.value = true;
  try {
    cart.value = await cherryPickApi.getCart();
  } catch (error) {
    console.error('Failed to load pick cart:', error);
  } finally {
    cartLoading.value = false;
  }
}

/** 加入购物车（跨任务连续加购；返回 {added, missing, duplicated}） */
async function addToCart(resultIds: number[]) {
  const outcome = await cherryPickApi.addToCart(resultIds);
  await refreshCart();
  return outcome;
}

/** 移除单条 */
async function removeItem(itemId: number) {
  const outcome = await cherryPickApi.removeFromCart([itemId]);
  await refreshCart();
  return outcome;
}

/** 批量移除（一键移除失效条目，§10） */
async function removeItems(itemIds: number[]) {
  const outcome = await cherryPickApi.removeFromCart(itemIds);
  await refreshCart();
  return outcome;
}

/** 清空购物车 */
async function clearCart() {
  const outcome = await cherryPickApi.clearCart();
  await refreshCart();
  return outcome;
}

/** 另存为挑选集（同名允许重复保存） */
async function saveAsSet(name: string, description?: string) {
  savingSet.value = true;
  try {
    const outcome = await cherryPickApi.saveAsSet(name, description);
    await refreshSets();
    return outcome;
  } finally {
    savingSet.value = false;
  }
}

async function refreshSets() {
  try {
    const data = await cherryPickApi.listSets();
    sets.value = data.items ?? [];
  } catch (error) {
    console.error('Failed to load pick sets:', error);
  }
}

/** 挑选集恢复进购物车 */
async function restoreSetToCart(setId: number) {
  const outcome = await cherryPickApi.restoreSetToCart(setId);
  await refreshCart();
  return outcome;
}

/** 删除挑选集 */
async function deleteSet(setId: number) {
  const outcome = await cherryPickApi.deleteSet(setId);
  await refreshSets();
  return outcome;
}

/** 全部条目平铺（下单向导统计用） */
function allItems(): PickCartItem[] {
  return cart.value.groups.flatMap((g: PickCartGroup) => g.items);
}

export function usePickCart() {
  return {
    // 状态
    cart, cartLoading, cartCount, invalidCount, savingSet, sets,
    // 购物车
    refreshCart, addToCart, removeItem, removeItems, clearCart, allItems,
    // 挑选集
    refreshSets, saveAsSet, restoreSetToCart, deleteSet,
  };
}
