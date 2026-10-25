// -*- coding: utf-8 -*-
/**
 * 挑选合并容器 · 下单成功落点（INT-1835 · 规范 18 §3 / §3.1 / §8.4）。
 *
 * 纯函数与 DOM 小工具，供 `Tasks.vue` / `TaskDetailModal.vue` / `TaskDetailView.vue` 共用：
 * - 落点地址：merge 出口带 `?focus=composition`，reexecute / reevaluate 不带（§3.1）；
 *   Vue 是 hash 路由（`createWebHashHistory`），只能走 query，`#composition` 会被当成路由片段（G6）。
 * - 定位：组成区 `#composition` 滚到**最近的可滚动祖先**（模态窗内容区 / 布局主内容区）顶部，
 *   `prefers-reduced-motion` 下无平滑滚动。
 * - 高亮：外描边类 1.2s 后移除（样式在宿主组件 `<style scoped>`，含 reduced-motion 分支）。
 */

/** 落点查询参数名与取值（§3.1，写死避免各处漂移） */
export const COMPOSITION_FOCUS_QUERY = 'focus';
export const COMPOSITION_FOCUS_VALUE = 'composition';

/** 组成区高亮类名与持续时长（§8.4：外描边 1.2s 渐隐） */
export const COMPOSITION_FOCUS_HIGHLIGHT_CLASS = 'is-composition-focus';
export const COMPOSITION_FOCUS_HIGHLIGHT_MS = 1200;

/** 组成区锚点（`ContainerComposition` 根节点 id） */
export const COMPOSITION_ANCHOR_ID = 'composition';

type QueryValue = string | null | undefined | (string | null)[];

/** `?focus=composition` 判定（重复参数数组形态也认） */
export function isCompositionFocusRequested(value: QueryValue): boolean {
  if (Array.isArray(value)) return value.includes(COMPOSITION_FOCUS_VALUE);
  return value === COMPOSITION_FOCUS_VALUE;
}

/**
 * 任务详情落点地址（§3.1）：merge 出口落到容器详情并聚焦组成区；
 * reexecute / reevaluate 出口保持原行为（不带参数）。
 */
export function taskDetailLocation(
  action: string,
  taskId: number | string,
): { path: string; query?: Record<string, string> } {
  const path = `/tasks/${String(taskId)}`;
  if (action === 'merge') {
    return { path, query: { [COMPOSITION_FOCUS_QUERY]: COMPOSITION_FOCUS_VALUE } };
  }
  return { path };
}

/** 系统是否要求减少动态效果（SSR / 测试环境无 matchMedia → 视为否） */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** 滚动行为：动效受限时直接跳转（motion-safe） */
export function focusScrollBehavior(): ScrollBehavior {
  return prefersReducedMotion() ? 'auto' : 'smooth';
}

/**
 * 元素最近的可滚动祖先（`overflow-y: auto|scroll|overlay` 且内容溢出）。
 * 详情为模态窗时是 `.modal-scroll-container`，路由页语境是布局 `.main-content`——
 * 都不滚动 window（§3 落点①）。
 */
export function resolveScrollContainer(el: Element | null | undefined): HTMLElement | null {
  if (!el || typeof window === 'undefined') return null;
  let node: HTMLElement | null = el.parentElement;
  while (node) {
    const style = window.getComputedStyle(node);
    const overflowY = style?.overflowY ?? '';
    const scrollable = overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay';
    if (scrollable && node.scrollHeight > node.clientHeight) return node;
    node = node.parentElement;
  }
  return null;
}

/** 把元素滚到容器顶部（`block: 'start'`）；返回是否发生了滚动调用 */
export function scrollElementToContainerTop(el: HTMLElement, container: HTMLElement): boolean {
  const offset = el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
  const top = Math.max(0, Math.round(offset));
  if (typeof container.scrollTo === 'function') {
    container.scrollTo({ top, behavior: focusScrollBehavior() });
    return true;
  }
  container.scrollTop = top;
  return true;
}

/** 组成区滚入可视区：优先滚最近的容器，无容器时退回 `scrollIntoView` */
export function scrollCompositionIntoView(el: HTMLElement): boolean {
  const container = resolveScrollContainer(el);
  if (container) return scrollElementToContainerTop(el, container);
  if (typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ block: 'start', behavior: focusScrollBehavior() });
    return true;
  }
  return false;
}

/** 按 id 取组成区锚点（无锚点时返回 null，不抛错） */
export function findCompositionAnchor(root?: Document | Element | null): HTMLElement | null {
  const scope = root ?? (typeof document === 'undefined' ? null : document);
  if (!scope) return null;
  const el = scope.querySelector(`#${COMPOSITION_ANCHOR_ID}`);
  return el instanceof HTMLElement ? el : null;
}
