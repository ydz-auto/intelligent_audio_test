/**
 * 已发布任务 composable（Application 层：编排用例、缓存 ReadModel、只见 Domain）
 * 适配 V9.7.31 目录化结构（composables/publishedTask/），API 访问收敛到
 * @/infrastructure/api（publishedTasksApi）。
 */
import { ref, reactive } from 'vue';
import { publishedTasksApi } from '../../infrastructure/api';
import type {
  PublishedTaskDetail,
  PublishedTaskExecuteResult,
  PublishedTaskItem,
  PublishedTaskPage,
} from '../../domain/model/publishedTask';

/** 已发布任务状态枚举（与后端 published_tasks.status 一致） */
export const PublishedTaskStatusEnum = {
  PUBLISHED: 'published',
  ARCHIVED: 'archived',
} as const;

/** 时间范围 → start_date/end_date（后端契约 ISO 字符串） */
function buildTimeRangeParams(timeRange: string, customRange: { start: string; end: string }): { startDate?: string; endDate?: string } {
  const today = new Date();
  const fmt = (d: Date) => {
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T00:00:00`;
  };
  if (timeRange === 'today') return { startDate: fmt(today) };
  if (timeRange === 'yesterday') {
    const y = new Date(today);
    y.setDate(y.getDate() - 1);
    return { startDate: fmt(y), endDate: fmt(today) };
  }
  if (timeRange === 'week') {
    const s = new Date(today);
    s.setDate(s.getDate() - 6);
    return { startDate: fmt(s) };
  }
  if (timeRange === 'month') {
    const s = new Date(today);
    s.setDate(s.getDate() - 29);
    return { startDate: fmt(s) };
  }
  if (timeRange === 'custom' && customRange.start) {
    return { startDate: `${customRange.start}T00:00:00`, endDate: customRange.end ? `${customRange.end}T23:59:59` : undefined };
  }
  return {};
}

export function usePublishedTasks() {
  const items = ref<PublishedTaskItem[]>([]);
  const detail = ref<PublishedTaskDetail | null>(null);
  const total = ref(0);
  const page = ref(1);
  const perPage = ref(10);
  const pages = ref(0);
  const loading = ref(false);
  const actionLoading = ref(false);

  // 列表筛选（ReadModel 缓存于本 composable）
  const filters = ref<{
    status: string;
    keyword: string;
    timeRange: string;
    customRange: { start: string; end: string };
    sort: { field: string; order: 'asc' | 'desc' };
  }>({
    status: 'all',
    keyword: '',
    timeRange: 'all',
    customRange: { start: '', end: '' },
    sort: { field: 'publishedAt', order: 'desc' },
  });

  /** 前端排序（对当前页生效） */
  function sortItems() {
    const { field, order } = filters.value.sort;
    const dir = order === 'asc' ? 1 : -1;
    items.value = [...items.value].sort((a: any, b: any) => {
      const av = a[field];
      const bv = b[field];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }

  function toggleSort(field: string) {
    if (filters.value.sort.field === field) {
      filters.value.sort.order = filters.value.sort.order === 'asc' ? 'desc' : 'asc';
    } else {
      filters.value.sort = { field, order: 'desc' };
    }
    sortItems();
  }

  async function fetchList() {
    loading.value = true;
    try {
      const params: Record<string, any> = {
        page: page.value,
        perPage: perPage.value,
      };
      if (filters.value.status && filters.value.status !== 'all') params.status = filters.value.status;
      if (filters.value.keyword) params.keyword = filters.value.keyword;
      Object.assign(params, buildTimeRangeParams(filters.value.timeRange, filters.value.customRange));
      const list: PublishedTaskPage = await publishedTasksApi.getAll(params);
      items.value = list.items;
      total.value = list.total;
      page.value = list.page || page.value;
      perPage.value = list.perPage || perPage.value;
      pages.value = list.pages || 0;
      sortItems();
    } catch (error) {
      console.error('Failed to fetch published tasks:', error);
    } finally {
      loading.value = false;
    }
  }

  async function fetchDetail(id: number): Promise<PublishedTaskDetail | null> {
    try {
      detail.value = await publishedTasksApi.getOne(id);
      return detail.value;
    } catch (error) {
      console.error('Failed to fetch published task detail:', error);
      return null;
    }
  }

  async function publish(
    sourceTaskId: number,
    name: string,
    description?: string,
    publishReason?: string,
    benchmarkOptions?: { benchmark: boolean; benchmarkSuite?: string; benchmarkCategory?: string }
  ) {
    actionLoading.value = true;
    try {
      const data = await publishedTasksApi.publish({
        sourceTaskId,
        name,
        description,
        publishReason,
        ...benchmarkOptions,
      });
      await fetchList();
      return data?.id ?? null;
    } catch (error) {
      console.error('Failed to publish task:', error);
      throw error;
    } finally {
      actionLoading.value = false;
    }
  }

  async function execute(id: number): Promise<PublishedTaskExecuteResult | null> {
    actionLoading.value = true;
    try {
      const data = await publishedTasksApi.execute(id);
      await fetchList();
      return data ?? null;
    } catch (error) {
      console.error('Failed to execute published task:', error);
      throw error;
    } finally {
      actionLoading.value = false;
    }
  }

  async function createVersion(id: number, sourceTaskId?: number, name?: string, publishReason?: string) {
    actionLoading.value = true;
    try {
      const data = await publishedTasksApi.createVersion(id, { sourceTaskId, name, publishReason });
      await fetchList();
      return data?.id ?? null;
    } catch (error) {
      console.error('Failed to create published task version:', error);
      throw error;
    } finally {
      actionLoading.value = false;
    }
  }

  async function archive(id: number) {
    actionLoading.value = true;
    try {
      await publishedTasksApi.archive(id);
      await fetchList();
    } catch (error) {
      console.error('Failed to archive published task:', error);
      throw error;
    } finally {
      actionLoading.value = false;
    }
  }

  /** 重命名已发布任务（后端同步更新整个版本链） */
  async function rename(id: number, name: string) {
    actionLoading.value = true;
    try {
      await publishedTasksApi.update(id, { name });
      await fetchList();
    } catch (error) {
      console.error('Failed to rename published task:', error);
      throw error;
    } finally {
      actionLoading.value = false;
    }
  }

  function setPage(p: number) {
    page.value = p;
    fetchList();
  }

  const state = reactive({
    items,
    detail,
    total,
    page,
    perPage,
    pages,
    loading,
    actionLoading,
    filters,
    statusOptions: [
      { value: 'all', label: '全部状态' },
      { value: PublishedTaskStatusEnum.PUBLISHED, label: '已发布' },
      { value: PublishedTaskStatusEnum.ARCHIVED, label: '已归档' },
    ],
    fetchList,
    fetchDetail,
    publish,
    execute,
    createVersion,
    archive,
    rename,
    setPage,
    toggleSort,
  });

  return state;
}
