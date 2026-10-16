/**
 * INT-536：评估维度域可见性一致性审计修复回归。
 *
 * D3：评估维度表操作入口（上移/下移/编辑/添加子维度/测试API/删除）按 canEditResource 门控——
 *     非 owner 私有维度隐藏全部操作入口；owner/admin 保留；共享维度回落既有权限点保留。
 * D4：维度行提供「设为共享/设为私有」切换按钮，走 PATCH /evaluation/dimensions/{id}/visibility
 *     （evaluationPort.updateVisibility），切换成功重取列表即时刷新徽标。
 * D5：新建维度表单默认取 localStorage visibility_pref（不再恒 shared）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { ref } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
  getCategories: vi.fn(),
  healthCheck: vi.fn(),
  update: vi.fn(),
  updateVisibility: vi.fn(),
  create: vi.fn(),
  delete: vi.fn(),
  import: vi.fn(),
  export: vi.fn(),
  reorder: vi.fn(),
}));
const algorithmApi = vi.hoisted(() => ({ getOptions: vi.fn() }));
const modal = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock('@/composables/evaluation/evaluationPort', () => ({ evaluationPort: ports }));
vi.mock('@/composables/algorithm/algorithmPort', () => ({ algorithmPort: algorithmApi }));
vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({
    open: modal.open,
    close: vi.fn(),
    closeAll: vi.fn(),
    getActiveModals: vi.fn(() => []),
    updateModalProps: vi.fn(),
    registerModal: vi.fn(),
  }),
  MODAL_TYPES: {
    BASIC_CONFIRM: 'basicConfirm',
    DELETE_CONFIRM: 'deleteConfirm',
    DETAIL_VIEW: 'detailView',
    CRUD_FORM: 'crudForm',
  },
}));
vi.mock('@/composables/modal/useNotification', () => ({
  provideNotification: vi.fn(),
  useNotification: () => ({ show: vi.fn(), success: vi.fn(), error: vi.fn() }),
}));
vi.mock('../../components/common/BadgeFilter.vue', () => ({
  default: { template: '<div class="badge-filter-stub" />', props: ['options', 'modelValue', 'allLabel', 'title'] },
}));
vi.mock('../../components/algorithm/AlgorithmFilter.vue', () => ({
  default: { template: '<div class="algorithm-filter-stub" />', props: ['options', 'modelValue', 'title'] },
}));

import Evaluation from '../Evaluation.vue';
import EvaluationDimensionTable from '@/components/EvaluationDimensionTable.vue';
import { useEvaluationModals } from '../../../composables/evaluation/useEvaluationModals';

const EMPTY_CATEGORIES = { items: [], total: 0, page: 1, per_page: 1000, pages: 1 };
const EMPTY_ALGOS = { algorithms: [] };

/** 三主维度：共享 / 私有（他人）/ 私有（本人 owner） */
const DIMENSIONS_ALL = {
  items: [
    { id: 31, name: '共享维度', weight: 5, dimensionType: 'main', resultType: 'api', status: true, categoryId: null, visibility: 'shared', createdByUserId: 999 },
    { id: 32, name: '他人私有', weight: 5, dimensionType: 'main', resultType: 'api', status: true, categoryId: null, visibility: 'private', createdByUserId: 999 },
    { id: 33, name: '我的私有', weight: 5, dimensionType: 'main', resultType: 'api', status: true, categoryId: null, visibility: 'private', createdByUserId: 1 },
  ],
  total: 3, page: 1, per_page: 1000, pages: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: 1, username: 'tester', roleId: null, roleName: '', permissions: [] });
  localStorage.clear();
  ports.getAll.mockResolvedValue(DIMENSIONS_ALL);
  ports.getCategories.mockResolvedValue(EMPTY_CATEGORIES);
  algorithmApi.getOptions.mockResolvedValue(EMPTY_ALGOS);
  modal.open.mockResolvedValue(true);
});

/** 挂载页面 → 切到列表视图 → 等待首屏完成 */
async function mountListView() {
  const wrapper = mount(Evaluation);
  await flushPromises();
  await wrapper.find('button.btn-toggle[title="列表视图"]').trigger('click');
  await flushPromises();
  return wrapper;
}

const rowBy = (wrapper: any, name: string) =>
  wrapper.findComponent(EvaluationDimensionTable).findAll('tbody tr').find((r: any) => r.text().includes(name));

describe('INT-536 D3：评估维度表操作入口 canEditResource 门控', () => {
  it('非 owner 私有维度：隐藏编辑/删除/上移/下移/测试API/添加子维度入口', async () => {
    const wrapper = await mountListView();
    const row = rowBy(wrapper, '他人私有');
    expect(row, '他人私有维度行应渲染').toBeTruthy();
    expect(row!.text()).not.toContain('编辑');
    expect(row!.text()).not.toContain('删除');
    expect(row!.text()).not.toContain('上移');
    expect(row!.text()).not.toContain('下移');
    expect(row!.text()).not.toContain('测试API');
    expect(row!.text()).not.toContain('设为共享');
  });

  it('owner 私有维度：保留编辑/删除等操作入口，切换按钮显示「设为共享」', async () => {
    const wrapper = await mountListView();
    const row = rowBy(wrapper, '我的私有');
    expect(row!.text()).toContain('编辑');
    expect(row!.text()).toContain('删除');
    expect(row!.text()).toContain('设为共享');
  });

  it('共享维度：操作入口保留（回落既有权限点），切换按钮显示「设为私有」', async () => {
    const wrapper = await mountListView();
    const row = rowBy(wrapper, '共享维度');
    expect(row!.text()).toContain('编辑');
    expect(row!.text()).toContain('删除');
    expect(row!.text()).toContain('设为私有');
  });
});

describe('INT-536 D4：维度可见性切换走 PATCH + 列表刷新', () => {
  it('点击「设为共享」→ updateVisibility(id, shared) → 重取列表刷新徽标', async () => {
    const wrapper = await mountListView();
    const row = rowBy(wrapper, '我的私有');
    const toggleBtn = row!.findAll('button').find((b: any) => b.text().includes('设为共享'));
    expect(toggleBtn, 'owner 私有维度应提供「设为共享」切换入口').toBeTruthy();

    await toggleBtn!.trigger('click');
    await flushPromises();

    expect(ports.updateVisibility).toHaveBeenCalledWith(33, 'shared');
    // 切换成功后 fetchData 重取（mounted 1 次 + 切换后 1 次）
    expect(ports.getAll).toHaveBeenCalledTimes(2);
  });

  it('切换失败：不刷新列表并提示（updateVisibility reject 收敛）', async () => {
    ports.updateVisibility.mockRejectedValueOnce(new Error('无权限'));
    const wrapper = await mountListView();
    const row = rowBy(wrapper, '我的私有');
    const toggleBtn = row!.findAll('button').find((b: any) => b.text().includes('设为共享'));
    await toggleBtn!.trigger('click');
    await flushPromises();

    expect(ports.updateVisibility).toHaveBeenCalledTimes(1);
    // 失败不触发重取
    expect(ports.getAll).toHaveBeenCalledTimes(1);
  });
});

describe('INT-536 D5：新建维度默认取 visibility_pref', () => {
  /** 直连 useEvaluationModals：注入最小 mock 模块，断言 openAddModal formData */
  function buildModals() {
    const dimsModule = {
      loading: { value: false },
      dimensions: ref([]),
      categories: ref([]),
      dimensionTemplate: { rule: { rules: [] }, requiredInputs: [] },
      evaluationFields: ref([]),
      saveDimension: vi.fn(),
    };
    const catsModule = { saveCategory: vi.fn() };
    return useEvaluationModals(dimsModule as any, catsModule as any);
  }

  it('localStorage 偏好 private → openAddModal formData.visibility = private', () => {
    localStorage.setItem('visibility_pref', 'private');
    const modals = buildModals();
    modals.openAddModal();
    const call = modal.open.mock.calls[modal.open.mock.calls.length - 1];
    expect(call[0]).toBe('crudForm');
    expect(call[1].formData.visibility).toBe('private');
  });

  it('localStorage 偏好 shared → openAddModal formData.visibility = shared', () => {
    localStorage.setItem('visibility_pref', 'shared');
    const modals = buildModals();
    modals.openAddModal();
    const call = modal.open.mock.calls[modal.open.mock.calls.length - 1];
    expect(call[1].formData.visibility).toBe('shared');
  });

  it('无偏好（缺省）→ openAddModal formData.visibility = shared', () => {
    const modals = buildModals();
    modals.openAddModal();
    const call = modal.open.mock.calls[modal.open.mock.calls.length - 1];
    expect(call[1].formData.visibility).toBe('shared');
  });
});
