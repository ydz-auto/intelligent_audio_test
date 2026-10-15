// -*- coding: utf-8 -*-
/**
 * 挑选合并任务列表 composable（INT-339，与 useMergedTasks 同构）。
 *
 * 数据源：GET /tasks?cherry_pick=true（task_cherry_pick_relations 存在性判定
 * 容器任务，§5.4——不使用 task.type）。筛选排序结构与日常/合并视图统一，
 * 由 Tasks 页共享筛选栏绑定（currentFilter 适配器）。
 */
import { ref, reactive } from 'vue';
import { tasksApi } from '../../infrastructure/api';
import type { Task } from '../../domain/model/task';

export function useCherryPickTasks() {
  const items = ref<Task[]>([]);
  const total = ref(0);
  const page = ref(1);
  const perPage = ref(10);
  const pages = ref(0);
  const loading = ref(false);

  // 统一筛选排序状态（cherry_pick=true 恒定下发；status 默认空 = 全部）
  const filters = reactive({
    search: '',
    status: 'all',
    algorithmType: 'all',
    timeRange: 'all',
    customRange: { start: '', end: '' },
    sort: { field: 'createdAt', order: 'desc' as 'asc' | 'desc' },
  });

  function buildTimeRangeParams(): { startTime?: string; endTime?: string } {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    switch (filters.timeRange) {
      case 'today':
        return { startTime: today.toISOString() };
      case 'yesterday': {
        const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
        return { startTime: yesterday.toISOString(), endTime: today.toISOString() };
      }
      case 'week': {
        const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
        return { startTime: weekAgo.toISOString() };
      }
      case 'month': {
        const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
        return { startTime: monthAgo.toISOString() };
      }
      case 'custom': {
        const range: { startTime?: string; endTime?: string } = {};
        if (filters.customRange.start) {
          range.startTime = new Date(filters.customRange.start).toISOString();
        }
        if (filters.customRange.end) {
          const endDate = new Date(filters.customRange.end);
          endDate.setHours(23, 59, 59, 999);
          range.endTime = endDate.toISOString();
        }
        return range;
      }
      default:
        return {};
    }
  }

  async function fetchList() {
    loading.value = true;
    try {
      const params: Record<string, any> = {
        page: page.value,
        perPage: perPage.value,
        cherryPick: true,
      };
      if (filters.search) params.search = filters.search;
      // 挑选合并视图状态筛选（all/completed，容器创建即 completed）
      if (filters.status && filters.status !== 'all') params.status = filters.status;
      if (filters.algorithmType && filters.algorithmType !== 'all') params.algorithmType = filters.algorithmType;
      Object.assign(params, buildTimeRangeParams());
      const data = await tasksApi.getAll(params) as any;
      items.value = data.items ?? [];
      total.value = data.total ?? 0;
      page.value = data.page || page.value;
      perPage.value = data.perPage || perPage.value;
      pages.value = data.pages ?? 0;
      sortItems();
    } catch (error) {
      console.error('Failed to fetch cherry-pick tasks:', error);
    } finally {
      loading.value = false;
    }
  }

  /** 前端排序（对当前页生效，对齐合并视图 sortItems 口径） */
  function sortItems() {
    const { field, order } = filters.sort;
    const dir = order === 'asc' ? 1 : -1;
    items.value = [...items.value].sort((a: any, b: any) => {
      const av = (a as any)[field];
      const bv = (b as any)[field];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }

  function toggleSort(field: string) {
    if (filters.sort.field === field) {
      filters.sort.order = filters.sort.order === 'asc' ? 'desc' : 'asc';
    } else {
      filters.sort = { field, order: 'desc' };
    }
    sortItems();
  }

  /** 筛选变更：回到第一页并重拉 */
  function apply() {
    page.value = 1;
    fetchList();
  }

  function setPage(p: number) {
    page.value = p;
    fetchList();
  }

  function setPageSize(size: number) {
    perPage.value = size;
    page.value = 1;
    fetchList();
  }

  function refresh() {
    fetchList();
  }

  return reactive({
    items,
    total,
    page,
    perPage,
    pages,
    loading,
    filters,
    fetchList,
    toggleSort,
    apply,
    setPage,
    setPageSize,
    refresh,
  });
}
