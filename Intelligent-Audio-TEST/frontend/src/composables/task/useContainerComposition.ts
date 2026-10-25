// -*- coding: utf-8 -*-
/**
 * 挑选合并容器（合并后任务）识别与信息头数据（INT-1832 · 规范 18 §2.2/§2.3/§12）。
 *
 * 容器识别写死于 `source` 溯源端点（详情 `GET /tasks/{id}` 不返回 is_cherry_pick / merge_type）：
 * - 200 且 groups 非空        → 挑选合并容器（渲染信息头 + 组成区）；
 * - 200 且 groups = [] 且 is_cherry_pick=true → 仍是容器（关系行缺失异常态，组成区走「无来源记录」空态）；
 * - 200 且 is_cherry_pick=false（站内普通任务的**当前真实返回**，实测 200 + groups=[]，
 *   规范 §2.3 写作「400 / code:203」为旧口径）→ 非容器，静默；
 * - 任何 4xx / 5xx / 网络中断 → 非容器，静默。
 *
 * 非容器一律归一 null：不渲染徽章与组成区、不进错态、不重试——详情页绝不因这个
 * 可选增强区变成错误页（`request` 的既有抛错语义保持不变，异常在本层 try/catch 收敛）。
 *
 * Application 层：只见 Domain（camelCase），API 访问收敛到 infrastructure/api。
 */
import { computed, ref, unref, watch, type Ref } from 'vue';
import { cherryPickApi } from '../../infrastructure/api';
import type { PickSource } from '../../infrastructure/api/cherryPickApi';

export type ContainerTaskId = string | number | null | undefined;

/** 归一后的容器溯源数据（异常 / 契约缺字段一律 null = 非容器） */
function normalizeSource(data: unknown): PickSource | null {
  if (!data || typeof data !== 'object') return null;
  const candidate = data as Partial<PickSource>;
  if (!Array.isArray(candidate.groups)) return null;
  // 站内普通任务的真实返回是「200 + is_cherry_pick=false + groups=[]」，
  // 只有 is_cherry_pick 明确为 true 时，空 groups 才按容器（关系行缺失异常态）处理。
  if (candidate.groups.length === 0 && candidate.isCherryPick !== true) return null;
  return {
    taskId: Number(candidate.taskId),
    isCherryPick: candidate.isCherryPick !== false,
    total: Number(candidate.total ?? 0),
    groups: candidate.groups.map((g) => ({
      sourceTaskId: Number(g?.sourceTaskId ?? 0),
      sourceTaskName: String(g?.sourceTaskName ?? ''),
      results: Array.isArray(g?.results) ? g.results : [],
    })),
  };
}

export function useContainerComposition(taskId: Ref<ContainerTaskId>) {
  /** 容器溯源数据；null = 非挑选合并容器（静默） */
  const source = ref<PickSource | null>(null);
  const loading = ref(false);
  /** 首次判定已结束（信息头骨架的收起条件） */
  const settled = ref(false);

  // 竞态防护：任务切换时丢弃过期响应（详情模态窗可连续打开不同任务）
  let token = 0;

  const isContainer = computed(() => source.value !== null);
  const sourceTaskCount = computed(() => source.value?.groups?.length ?? 0);
  const sourceResultCount = computed(() => source.value?.total ?? 0);

  async function load(id: ContainerTaskId = unref(taskId)) {
    const current = ++token;
    if (id === null || id === undefined || id === '') {
      source.value = null;
      loading.value = false;
      settled.value = true;
      return;
    }
    loading.value = true;
    try {
      const data = await cherryPickApi.getSource(id as string | number);
      if (current !== token) return;
      source.value = normalizeSource(data);
    } catch {
      // 4xx / 5xx / 网络中断：非容器静默（不重试、不冒泡、不落错态）
      if (current !== token) return;
      source.value = null;
    } finally {
      if (current === token) {
        loading.value = false;
        settled.value = true;
      }
    }
  }

  watch(() => unref(taskId), (id) => { void load(id); }, { immediate: true });

  return {
    source,
    isContainer,
    sourceTaskCount,
    sourceResultCount,
    loading,
    settled,
    reload: () => load(),
  };
}
