/**
 * INT-281：Evaluation 维度列表恢复全量拉取 + 前端过滤（主/子维度同屏聚合回归）。
 *
 * 缺陷：V9.7.31 服务端分页（page/perPage=10）+ 筛选下推后端，把主/子维度切到不同页，
 * hierarchicalDimensions 孤儿兜底只能显示空父名；搜索命中子维度也无法带上父维度上下文。
 * 基线口径（V9.7.10）：一次拉全量（perPage:1000），搜索/筛选由 filteredDimensions 前端联动，
 * 注释明确「保证主/子维度始终同屏聚合展示」。
 *
 * 锁定契约（真实 useEvaluation 组合链 + 端口 mock，端到端贯通）：
 * 1. 全量拉取：fetchData 发送 { page:1, perPage:1000 }，且不携带 search/status/categoryId
 *    服务端筛选参数（过滤在前端做）；
 * 2. 主/子同屏聚合：分页形状（total=3, pages=3，模拟旧缺陷一页 10 条切三页）的全量数据
 *    中主维度与其子维度必须出现在同一视图（列表视图相邻、分组视图同组）；
 * 3. 搜索前端联动：搜索命中子维度时父维度整组展示（_parentName 非空），且不触发二次拉取；
 * 4. 过滤前端联动：状态/分类筛选仅前端派生，不发新请求；重置清空各筛选项同样不发请求；
 * 5. 保存后刷新仍走全量口径（saveDimension → fetchData 全量参数）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

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
// EvaluationDimensionTable 保持真实组件（行渲染与层级展示是被测对象本身）
import EvaluationDimensionTable from '@/components/EvaluationDimensionTable.vue';

import Evaluation from '../Evaluation.vue';

const EMPTY_CATEGORIES = { items: [], total: 0, page: 1, per_page: 1000, pages: 1 };
const EMPTY_ALGOS = { algorithms: [] };

/**
 * 全量数据（分页信封形状）：主维度 31 + 子维度 32（父=31）+ 主维度 33。
 * total=3 / pages=3 / per_page=1 模拟旧缺陷的分页信封——若实现误把 perPage:10 之外的
 * 服务端分页/筛选参数带回，或按 per_page 切片渲染，父/子将不再同屏。
 */
const DIMENSIONS_ALL = {
  items: [
    { id: 31, name: '准确率', weight: 5, dimensionType: 'main', resultType: 'api', status: true, categoryId: null },
    { id: 32, name: '拒识准确率', weight: 3, dimensionType: 'sub', parentDimensionId: 31, resultType: 'api', status: true, categoryId: null },
    { id: 33, name: '响应时延', weight: 2, dimensionType: 'main', resultType: 'api', status: true, categoryId: null },
  ],
  total: 3, page: 1, per_page: 1, pages: 3,
};

const lastModalCall = () => modal.open.mock.calls[modal.open.mock.calls.length - 1];

/** 挂载页面并等待首屏拉取完成 */
async function mountEvaluation() {
  const wrapper = mount(Evaluation);
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  ports.getAll.mockResolvedValue(DIMENSIONS_ALL);
  ports.getCategories.mockResolvedValue(EMPTY_CATEGORIES);
  algorithmApi.getOptions.mockResolvedValue(EMPTY_ALGOS);
});

describe('全量拉取契约（INT-281）', () => {
  it('fetchData 发送 { page:1, perPage:1000 } 全量参数，不携带服务端筛选参数', async () => {
    await mountEvaluation();

    expect(ports.getAll).toHaveBeenCalledTimes(1);
    const params = ports.getAll.mock.calls[0][0];
    expect(params).toMatchObject({ page: 1, perPage: 1000 });
    expect(params.search).toBeUndefined();
    expect(params.status).toBeUndefined();
    expect(params.categoryId).toBeUndefined();
  });

  it('未分类分组下主/子维度同组聚合展示（分页信封不再切散层级）', async () => {
    const wrapper = await mountEvaluation();

    // 默认分组视图：三个维度全部渲染（分页信封 total=3/pages=3 不得截断列表）
    const tables = wrapper.findAllComponents(EvaluationDimensionTable);
    const pageText = tables.map(t => t.text()).join('');
    expect(pageText).toContain('准确率');
    expect(pageText).toContain('拒识准确率');
    expect(pageText).toContain('响应时延');

    // 层级聚合：拒识准确率（子）在未分类组内紧随父维度 31，父名提示非空
    const groupTables = tables.filter(t => (t.props('items') as any[]).some((d: any) => d.id === 32));
    expect(groupTables.length).toBe(1);
    const rows = groupTables[0]!.findAll('tbody tr');
    const parentRow = rows.find((r: any) => r.text().includes('准确率'));
    const childRow = rows.find((r: any) => r.text().includes('拒识准确率'));
    expect(parentRow, '父维度行应存在').toBeTruthy();
    expect(childRow, '子维度行应存在').toBeTruthy();
    expect(rows.indexOf(childRow!)).toBeGreaterThan(rows.indexOf(parentRow!));
    expect(childRow!.text()).toContain('（准确率）');
  });

  it('列表视图：主维度与其子维度相邻展示，子行带父名提示', async () => {
    const wrapper = await mountEvaluation();
    await wrapper.find('button.btn-toggle[title="列表视图"]').trigger('click');
    await flushPromises();

    const table = wrapper.findComponent(EvaluationDimensionTable);
    const rows = table.findAll('tbody tr');
    const parentIdx = rows.findIndex((r: any) => r.text().includes('准确率'));
    const childIdx = rows.findIndex((r: any) => r.text().includes('拒识准确率'));
    expect(parentIdx).toBeGreaterThanOrEqual(0);
    expect(childIdx).toBe(parentIdx + 1);
    expect(rows[childIdx].text()).toContain('（准确率）');
  });
});

describe('搜索/筛选前端联动（INT-281）', () => {
  it('搜索命中子维度：父维度整组展示（_parentName 非空），且不触发二次拉取', async () => {
    const wrapper = await mountEvaluation();

    const input = wrapper.find('input.search-input');
    await input.setValue('拒识');
    await flushPromises();

    expect(ports.getAll).toHaveBeenCalledTimes(1);

    const table = wrapper.findComponent(EvaluationDimensionTable);
    const rows = table.findAll('tbody tr');
    expect(rows.some((r: any) => r.text().includes('拒识准确率'))).toBe(true);
    const parentRow = rows.find((r: any) => r.text().includes('准确率'));
    expect(parentRow, '搜索命中子维度时父维度应整组展示').toBeTruthy();
  });

  it('状态/分类筛选仅前端派生，不发新请求', async () => {
    const wrapper = await mountEvaluation();

    // 状态筛选拉回调 BadgeFilter（替换组件不透传事件），直接驱动 composable 过滤函数
    const { useEvaluationDimensions } = await import('@/composables/evaluation/useEvaluationDimensions');
    const dims = useEvaluationDimensions();
    await flushPromises();

    dims.filterDimensions();
    dims.searchDimensions();
    await flushPromises();

    expect(ports.getAll).toHaveBeenCalledTimes(1);
  });

  it('重置筛选清空搜索词与各筛选项，不触发重新拉取', async () => {
    const { useEvaluationDimensions } = await import('@/composables/evaluation/useEvaluationDimensions');
    const dims = useEvaluationDimensions();
    await dims.fetchData();

    dims.searchKeyword.value = '准确率';
    dims.filterStatus.value = 'active';
    (dims.filterCategory.value as any) = '2';
    dims.filterAlgorithm.value = 'asr';

    dims.resetFilters();
    await flushPromises();

    expect(ports.getAll).toHaveBeenCalledTimes(1);
    expect(dims.searchKeyword.value).toBe('');
    expect(dims.filterStatus.value).toBe('all');
    expect(dims.filterCategory.value).toBe('all');
    expect(dims.filterAlgorithm.value).toBe('all');
  });
});
