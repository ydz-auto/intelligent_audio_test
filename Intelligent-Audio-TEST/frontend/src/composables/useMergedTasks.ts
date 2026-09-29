/**
 * 合并任务 composable（Application 层：编排用例、缓存 ReadModel，只见 Domain）
 * 对齐《任务合并功能设计文档》：拉取 type='merged' 的任务及其来源任务。
 * 筛选排序结构与日常/发布视图统一（共享 utils/filterUtils）。
 */
import { ref, reactive } from 'vue';
import { tasksApi } from '../utils/api';
import { buildTimeRangeParams, sortTasks } from '../utils/filterUtils';
import type { MergedTaskItem, MergedTaskPage } from '../domain/model/mergedTask';

export function useMergedTasks() {
  const items = ref<MergedTaskItem[]>([]);
  const total = ref(0);
  const page = ref(1);
  const perPage = ref(10);
  const pages = ref(0);
  const loading = ref(false);

  // 统一筛选排序状态（type 恒为 merged；algorithmType 走后端 test_tasks.algorithm_type 过滤）
  const filters = reactive({
    search: '',
    status: 'all',
    algorithmType: 'all',
    timeRange: 'all',
    customRange: { start: '', end: '' },
    sort: { field: 'createdAt', order: 'desc' as 'asc' | 'desc' },
  });

  async function fetchList() {
    loading.value = true;
    try {
      const params: Record<string, any> = {
        page: page.value,
        per_page: perPage.value,
        type: 'merged',
      };
      if (filters.search) params.search = filters.search;
      if (filters.status && filters.status !== 'all') params.status = filters.status;
      if (filters.algorithmType && filters.algorithmType !== 'all') params.algorithm_type = filters.algorithmType;
      Object.assign(params, buildTimeRangeParams(filters.timeRange, filters.customRange));
      const data = (await tasksApi.getAll(params)) as any;
      const payload = data?.data ?? data ?? {};
      const list: MergedTaskPage = payload?.items
        ? payload
        : { items: payload || [], total: 0, page: page.value, perPage: perPage.value, pages: 0 };
      items.value = list.items;
      total.value = list.total;
      page.value = list.page || page.value;
      perPage.value = list.perPage || perPage.value;
      pages.value = list.pages || 0;
      sortItems();
    } catch (error) {
      console.error('Failed to fetch merged tasks:', error);
    } finally {
      loading.value = false;
    }
  }

  /** 前端排序（对齐日常视图，对当前页生效） */
  function sortItems() {
    items.value = sortTasks(items.value, filters.sort);
  }

  function toggleSort(field: string) {
    if (filters.sort.field === field) {
      filters.sort.order = filters.sort.order === 'asc' ? 'desc' : 'asc';
    } else {
      filters.sort = { field, order: 'desc' };
    }
    sortItems();
  }

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

  // reactive 包裹：模板中可直接访问 items/total/page 等（嵌套 ref 自动解包），
  // 方法一并放入 reactive，保证返回类型包含全部 API。
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
