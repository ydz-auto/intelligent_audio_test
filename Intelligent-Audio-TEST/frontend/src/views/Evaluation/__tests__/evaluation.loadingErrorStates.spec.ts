/**
 * INT-290：Evaluation 列表页加载/错误态缺失回归。
 *
 * 缺陷（INT-261 C 域 UX 审计）：loaders.ts 写入 error.value='获取评估维度失败' 但模板从未渲染；
 * 列表视图无任何 loading 指示（仅分组视图有）。锁定契约：
 * 1. 加载态：请求挂起期间列表/分组两视图均渲染 .evaluation-loading-bar（对齐 A/B 域 Device loading bar），
 *    且不闪「暂无评估维度数据」空态；
 * 2. 错误态：fetch 失败渲染 .evaluation-error-banner（含错误文案 + 重试按钮），空态被抑制；
 * 3. 重试：点击重试重新拉取，成功后错误条消失、维度正常渲染。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { nextTick } from 'vue';

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
  getCategories: vi.fn(),
  healthCheck: vi.fn(),
  update: vi.fn(),
  create: vi.fn(),
  delete: vi.fn(),
  import: vi.fn(),
  export: vi.fn(),
  reorder: vi.fn(),
}));
const algorithmApi = vi.hoisted(() => ({
  getOptions: vi.fn(),
}));
const modal = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock('@/composables/evaluation/evaluationPort', () => ({
  evaluationPort: ports,
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: algorithmApi,
}));

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
  },
}));

vi.mock('@/composables/modal/useNotification', () => ({
  provideNotification: vi.fn(),
  useNotification: () => ({ show: vi.fn() }),
}));

// 子组件浅替身：页面级 wire 契约测试不渲染其内部
vi.mock('../../components/common/BadgeFilter.vue', () => ({
  default: { template: '<div class="badge-filter-stub" />', props: ['options', 'modelValue', 'allLabel', 'title'] },
}));
vi.mock('../../components/algorithm/AlgorithmFilter.vue', () => ({
  default: { template: '<div class="algorithm-filter-stub" />', props: ['options', 'modelValue', 'title'] },
}));
// EvaluationDimensionTable 保持真实组件（行渲染与空态抑制是被测对象本身）
import EvaluationDimensionTable from '@/components/EvaluationDimensionTable.vue';

import Evaluation from '../Evaluation.vue';

const EMPTY_CATEGORIES = { items: [], total: 0, page: 1, per_page: 1000, pages: 1 };
const EMPTY_ALGOS = { algorithms: [] };

/** 全量数据（分页信封形状，与 INT-281 契约一致） */
const DIMENSIONS_ALL = {
  items: [
    { id: 31, name: '准确率', weight: 5, dimensionType: 'main', resultType: 'api', status: true, categoryId: null },
    { id: 32, name: '拒识准确率', weight: 3, dimensionType: 'sub', parentDimensionId: 31, resultType: 'api', status: true, categoryId: null },
  ],
  total: 2, page: 1, per_page: 1, pages: 2,
};

/** 可手动 resolve 的延迟 Promise（模拟请求挂起） */
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  ports.getAll.mockResolvedValue(DIMENSIONS_ALL);
  ports.getCategories.mockResolvedValue(EMPTY_CATEGORIES);
  algorithmApi.getOptions.mockResolvedValue(EMPTY_ALGOS);
});

describe('加载态（INT-290）', () => {
  it('请求挂起期间：分组视图（默认）与列表视图均渲染 loading bar，且不闪空态', async () => {
    const d = deferred<any>();
    ports.getAll.mockReturnValue(d.promise);

    const wrapper = mount(Evaluation);
    await nextTick();

    // 默认分组视图
    expect(wrapper.find('.evaluation-loading-bar').exists()).toBe(true);
    expect(wrapper.find('.empty-dimensions').exists()).toBe(false);

    // 切换列表视图（加载中切换同样有指示）
    await wrapper.find('button.btn-toggle[title="列表视图"]').trigger('click');
    await nextTick();
    expect(wrapper.find('.evaluation-loading-bar').exists()).toBe(true);

    d.resolve(DIMENSIONS_ALL);
    await flushPromises();

    expect(wrapper.find('.evaluation-loading-bar').exists()).toBe(false);
  });
});

describe('错误态（INT-290）', () => {
  it('fetch 失败：渲染错误条（含「获取评估维度失败」与重试按钮），空态被抑制', async () => {
    ports.getAll.mockRejectedValue(new Error('net down'));

    const wrapper = mount(Evaluation);
    await flushPromises();

    const banner = wrapper.find('.evaluation-error-banner');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain('获取评估维度失败');
    expect(banner.text()).toContain('重试');
    // 错误态下不显示「暂无评估维度数据」空态
    expect(wrapper.find('.empty-dimensions').exists()).toBe(false);
  });

  it('列表视图同样渲染错误条（此前 error 仅写入状态、两视图均无消费）', async () => {
    ports.getAll.mockRejectedValue(new Error('net down'));

    const wrapper = mount(Evaluation);
    await flushPromises();
    await wrapper.find('button.btn-toggle[title="列表视图"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('.evaluation-error-banner').exists()).toBe(true);
    expect(wrapper.find('.evaluation-error-banner').text()).toContain('获取评估维度失败');
  });

  it('重试按钮：点击后重新拉取，成功后错误条消失、维度正常渲染', async () => {
    ports.getAll.mockRejectedValueOnce(new Error('net down'));
    ports.getAll.mockResolvedValueOnce(DIMENSIONS_ALL);

    const wrapper = mount(Evaluation);
    await flushPromises();
    expect(wrapper.find('.evaluation-error-banner').exists()).toBe(true);

    await wrapper.find('.evaluation-error-banner .btn-sm').trigger('click');
    await flushPromises();

    expect(ports.getAll).toHaveBeenCalledTimes(2);
    expect(wrapper.find('.evaluation-error-banner').exists()).toBe(false);
    expect(wrapper.findAllComponents(EvaluationDimensionTable).length).toBeGreaterThan(0);
  });
});
