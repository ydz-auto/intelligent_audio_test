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
import { computed, reactive, ref, unref, watch, type Ref } from 'vue';
import { cherryPickApi } from '../../infrastructure/api';
import { toCompositionEntries } from '../../components/task/pick/compositionTree';
import type { PickSource } from '../../infrastructure/api/cherryPickApi';
import type { CompositionEntry } from '../../domain/model/containerComposition';
import type { Task } from '../../domain/model/task';
import { tasksPort } from './tasksPort';

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

// ===== 落点③ 挑选合并页签「行展开」：组成模型 + 补拉缓存（规范 18 §3/§4.3） =====

/** 行展开的组成模型：source + 详情补拉 join 后的组成条目（与详情侧组成区同源纯函数） */
export interface ContainerCompositionModel {
  /** 组成条目（任务视图默认等四视图的唯一数据源） */
  entries: CompositionEntry[]
  /** 来源任务数（source.groups.length） */
  taskCount: number
  /** 来源结果数（source.total） */
  resultCount: number
}

/**
 * 列表侧组成模型缓存：`Map<taskId, ContainerCompositionModel>`（§4.3 写死）。
 *
 * 列表 DTO 只有任务名与计数、没有 `cases[]`，所以首次展开补 1 次 `GET /tasks/{id}`；
 * **再次展开复用、收起不释放、不重复请求**。放模块级而非组件级：面板收起（组件卸载）、
 * 翻页 / 重新挂载回来都仍命中缓存，避免重复请求。
 */
const compositionModels = reactive(new Map<number, ContainerCompositionModel>());
/** 同一 taskId 的并发请求合并为一次（连点两行 / 展开重试竞态） */
const compositionInflight = new Map<number, Promise<ContainerCompositionModel>>();

/** 已缓存的组成模型（无缓存 → null） */
export function getContainerCompositionModel(
  taskId: number | string,
): ContainerCompositionModel | null {
  return compositionModels.get(Number(taskId)) ?? null;
}

/** 清空缓存（测试隔离 / 会话切换用；正常交互不释放） */
export function clearContainerCompositionCache(): void {
  compositionModels.clear();
  compositionInflight.clear();
}

/** 补拉详情 + 溯源，装配组成模型：`GET /tasks/{id}` 是列表行展开的唯一补拉请求 */
async function fetchContainerCompositionModel(
  taskId: number,
): Promise<ContainerCompositionModel> {
  const pending = compositionInflight.get(taskId);
  if (pending) return pending;
  const request = (async () => {
    // source 给来源分组 / 结果 id 级数据，详情给用例名 / 分组 / 标签 / 设备 API 名 join 源
    const [source, detail] = await Promise.all([
      cherryPickApi.getSource(taskId),
      tasksPort.getOne(taskId),
    ]);
    const task = detail as Task | null;
    const model: ContainerCompositionModel = {
      entries: toCompositionEntries(
        source,
        task?.cases ?? [],
        task?.devices ?? [],
        task?.apis ?? [],
      ),
      taskCount: source?.groups?.length ?? 0,
      resultCount: source?.total ?? 0,
    };
    return model;
  })();
  compositionInflight.set(taskId, request);
  try {
    return await request;
  } finally {
    compositionInflight.delete(taskId);
  }
}

/**
 * 落点③ 页签行展开 composable：命中缓存零请求，未命中补拉 1 次详情；
 * 失败不写缓存（展开区 Empty + 重试，行本体与计数照常，§7）。
 */
export function useContainerTraceComposition(taskId: Ref<ContainerTaskId>) {
  const loading = ref(false);
  const error = ref(false);
  // 竞态防护：换行展开 / 重试时丢弃过期响应
  let token = 0;

  const model = computed<ContainerCompositionModel | null>(() => {
    const id = unref(taskId);
    if (id === null || id === undefined || id === '') return null;
    return compositionModels.get(Number(id)) ?? null;
  });

  function hasId(value: ContainerTaskId): value is number | string {
    return value !== null && value !== undefined && value !== '';
  }

  async function load(force = false) {
    const current = ++token;
    const raw = unref(taskId);
    if (!hasId(raw)) {
      loading.value = false;
      error.value = false;
      return;
    }
    const key = Number(raw);
    if (!force && compositionModels.has(key)) {
      // 收起再展开：复用缓存，不重复请求
      loading.value = false;
      error.value = false;
      return;
    }
    loading.value = true;
    error.value = false;
    try {
      const next = await fetchContainerCompositionModel(key);
      if (current !== token) return;
      compositionModels.set(key, next);
    } catch {
      // 补拉失败：不写缓存（重试 / 再展开可重新请求）
      if (current !== token) return;
      error.value = true;
    } finally {
      if (current === token) loading.value = false;
    }
  }

  watch(
    () => unref(taskId),
    () => {
      error.value = false;
      void load();
    },
    { immediate: true },
  );

  return {
    model,
    loading,
    error,
    /** 重新检查缓存（不强制请求） */
    reload: () => load(),
    /** 补拉失败后的重试（强制重新请求） */
    retry: () => load(true),
  };
}
