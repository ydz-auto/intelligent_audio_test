/**
 * INT-255：PublishedTaskPanel 列表加载错误态渲染 —— 请求失败显示错误提示 + 重试入口，不落空态。
 *
 * 锁定契约：
 * 1. pt.loadError 置位 → 渲染 .pt-error（错误标题 + 明细 + 重试按钮），不渲染 .pt-empty 空态；
 * 2. 错误分类驱动标题（ListLoadErrorType 枚举）：NETWORK → 无法连接服务器 / SERVER → 服务器开小差了 / UNKNOWN → 已发布任务加载失败；
 * 3. 点击重试 → 调用 pt.fetchList()；
 * 4. 错误态下分页隐藏（error 优先于空态与分页）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const pushes = vi.hoisted(() => ({ list: [] as any[] }));
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: (loc: any) => pushes.list.push(loc) }),
}));

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: { getAll: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 100, pages: 0 })) },
}));

vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({ show: vi.fn(), error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() }),
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: vi.fn(), close: vi.fn(), closeAll: vi.fn(), getActiveModals: () => [], updateModalProps: vi.fn(), registerModal: vi.fn() }),
  getModalManager: () => ({ open: vi.fn(), close: vi.fn(), closeAll: vi.fn(), getActiveModals: () => [], updateModalProps: vi.fn(), registerModal: vi.fn() }),
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm', DELETE_CONFIRM: 'deleteConfirm' },
}));

import PublishedTaskPanel from '../PublishedTaskPanel.vue';
import { ListLoadErrorType } from '../../../domain/enums';
import type { PublishedTaskItem } from '../../../domain/model/publishedTask';

/** usePublishedTasks 状态替身（PublishedTaskPanel 仅消费该对象，不关心实现） */
function fakePt(overrides: Record<string, any> = {}) {
  return {
    items: [] as PublishedTaskItem[],
    detail: null as any,
    total: 0,
    page: 1,
    perPage: 10,
    pages: 0,
    loading: false,
    actionLoading: false,
    loadError: null as any,
    filters: {
      status: 'all', keyword: '', type: 'all', algorithmType: 'all',
      timeRange: 'all', customRange: { start: '', end: '' },
      sort: { field: 'publishedAt', order: 'desc' as const },
    },
    statusOptions: [],
    typeOptions: [],
    fetchList: vi.fn(async () => {}),
    fetchDetail: vi.fn(async () => null),
    publish: vi.fn(),
    execute: vi.fn(),
    createVersion: vi.fn(),
    archive: vi.fn(),
    rename: vi.fn(),
    setPage: vi.fn(),
    toggleSort: vi.fn(),
    ...overrides,
  } as any;
}

async function mountPanel(ptState: any = fakePt()) {
  const { createPinia, setActivePinia } = await import('pinia');
  const { useAuthStore } = await import('../../../store/authStore');
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: 1, username: 'u', roleId: null, roleName: '', permissions: ['*'] });

  const wrapper = mount(PublishedTaskPanel, {
    props: { pt: ptState },
    attachTo: document.body,
    global: {
      stubs: {
        PublishTaskModal: { template: '<div class="publish-task-modal-stub" />', props: ['tasks', 'submitting', 'presetSourceTaskId'] },
        ReportSnapshotModal: { template: '<div class="report-snapshot-modal-stub" />' },
        TaskSnapshotModal: { template: '<div class="task-snapshot-modal-stub" />' },
        PublishedTaskNameModal: { template: '<div class="published-task-name-modal-stub" />' },
      },
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  pushes.list.length = 0;
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('PublishedTaskPanel 列表加载错误态（INT-255）', () => {
  it('loadError 置位 → 渲染错误态 + 重试入口，不渲染空态', async () => {
    const w = await mountPanel(fakePt({ loadError: { type: ListLoadErrorType.NETWORK, message: 'Failed to fetch' } }));
    expect(w.find('.pt-error').exists()).toBe(true);
    expect(w.find('.pt-error-title').text()).toContain('无法连接服务器');
    expect(w.find('.pt-error-hint').text()).toContain('Failed to fetch');
    expect(w.find('.pt-error .btn').text()).toContain('重试');
    expect(w.find('.pt-empty').exists()).toBe(false);
    w.unmount();
  });

  it('错误分类驱动标题：SERVER → 服务器开小差了 / UNKNOWN → 已发布任务加载失败', async () => {
    const w1 = await mountPanel(fakePt({ loadError: { type: ListLoadErrorType.SERVER, message: 'Internal error' } }));
    expect(w1.find('.pt-error-title').text()).toContain('服务器开小差了');
    w1.unmount();

    const w2 = await mountPanel(fakePt({ loadError: { type: ListLoadErrorType.UNKNOWN, message: 'boom' } }));
    expect(w2.find('.pt-error-title').text()).toContain('已发布任务加载失败');
    w2.unmount();
  });

  it('错误态下空态与分页隐藏（error 优先，且不落空态）', async () => {
    const w = await mountPanel(fakePt({
      loadError: { type: ListLoadErrorType.SERVER, message: '500' },
      items: [],
      total: 3,
      pages: 1,
    }));
    expect(w.find('.pt-error').exists()).toBe(true);
    expect(w.find('.pt-empty').exists()).toBe(false);
    expect(w.find('.pt-pagination').exists()).toBe(false);
    w.unmount();
  });

  it('点击重试 → 调用 pt.fetchList()', async () => {
    const fetchList = vi.fn(async () => {});
    const w = await mountPanel(fakePt({ loadError: { type: ListLoadErrorType.NETWORK, message: 'x' }, fetchList }));
    const before = fetchList.mock.calls.length; // onMounted 首拉已触发 1 次
    await w.find('.pt-error .btn').trigger('click');
    expect(fetchList).toHaveBeenCalledTimes(before + 1);
    w.unmount();
  });
});
