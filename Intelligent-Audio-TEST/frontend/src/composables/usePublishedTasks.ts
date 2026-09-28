/**
 * 已发布任务 composable（Application 层：编排用例、缓存 ReadModel、只见 Domain）
 */
import { ref, computed, reactive } from 'vue';
import { publishedTasksApi } from '../utils/api';
import { buildTimeRangeParams, sortTasks } from '../utils/filterUtils';
import type {
  PublishedTaskDetail,
  PublishedTaskExecuteResult,
  PublishedTaskItem,
  PublishedTaskPage,
  PublishedTaskQuery,
} from '../domain/model/publishedTask';
import { PublishedTaskStatus } from '../domain/enums';

export function usePublishedTasks() {
  const items = ref<PublishedTaskItem[]>([]);
  const detail = ref<PublishedTaskDetail | null>(null);
  const total = ref(0);
  const page = ref(1);
  const perPage = ref(10);
  const pages = ref(0);
  const loading = ref(false);
  const actionLoading = ref(false);

  // 列表筛选（ReadModel 缓存于本 composable，不直接写后端主链路；结构与日常/合并视图对齐）
  const filters = ref<{
    status: string;
    keyword: string;
    type: string;
    timeRange: string;
    customRange: { start: string; end: string };
    sort: { field: string; order: 'asc' | 'desc' };
  }>({
    status: 'all',
    keyword: '',
    type: 'all',
    timeRange: 'all',
    customRange: { start: '', end: '' },
    sort: { field: 'publishedAt', order: 'desc' },
  });
  const filteredItems = computed(() => items.value);

  /** 前端排序（对齐日常视图，对当前页生效） */
  function sortItems() {
    items.value = sortTasks(items.value, filters.value.sort);
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
      if (filters.value.type && filters.value.type !== 'all') params.type = filters.value.type;
      Object.assign(params, buildTimeRangeParams(filters.value.timeRange, filters.value.customRange));
      const data = (await publishedTasksApi.getAll(params)) as any;
      const payload = data?.data ?? data ?? {};
      const list: PublishedTaskPage = payload?.items
        ? payload
        : { items: payload || [], total: 0, page: page.value, perPage: perPage.value, pages: 0 };
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

  async function fetchDetail(id: number) {
    try {
      const data = (await publishedTasksApi.getOne(id)) as any;
      detail.value = (data?.data ?? data) as PublishedTaskDetail;
      return detail.value;
    } catch (error) {
      console.error('Failed to fetch published task detail:', error);
      return null;
    }
  }

  async function publish(sourceTaskId: number, name: string, description?: string, publishReason?: string) {
    actionLoading.value = true;
    try {
      // 注意：request() 默认 unwrapResponse=true，已自动解包 data.data，这里直接取业务字段
      const data = (await publishedTasksApi.publish({ sourceTaskId, name, description, publishReason })) as any;
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
      const data = (await publishedTasksApi.execute(id)) as any;
      await fetchList();
      return (data ?? null) as PublishedTaskExecuteResult | null;
    } catch (error) {
      console.error('Failed to execute published task:', error);
      throw error;
    } finally {
      actionLoading.value = false;
    }
  }

  async function createVersion(id: number, sourceTaskId?: number, name?: string) {
    actionLoading.value = true;
    try {
      const data = (await publishedTasksApi.createVersion(id, { sourceTaskId, name })) as any;
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

  function setPage(p: number) {
    page.value = p;
    fetchList();
  }

  function setFilter(status: string, keyword: string) {
    filters.value.status = status;
    filters.value.keyword = keyword;
    page.value = 1;
    fetchList();
  }

  function resetFilters() {
    filters.value = {
      status: 'all',
      keyword: '',
      type: 'all',
      timeRange: 'all',
      customRange: { start: '', end: '' },
      sort: { field: 'publishedAt', order: 'desc' },
    };
    page.value = 1;
    fetchList();
  }

  // reactive 包裹：模板/script 中可直接访问 items/total/page 等（嵌套 ref 自动解包）。
  // 注意：不能 `{ ...state, ... }` 展开——展开 reactive 会把嵌套 ref 解包成静态值，丢失响应性。
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
    filteredItems,
    statusOptions: [
      { value: 'all', label: '全部状态' },
      { value: PublishedTaskStatus.PUBLISHED, label: '已发布' },
      { value: PublishedTaskStatus.ARCHIVED, label: '已归档' },
    ],
    fetchList,
    fetchDetail,
    publish,
    execute,
    createVersion,
    archive,
    setPage,
    setFilter,
    resetFilters,
    toggleSort,
  });

  return state;
}
