/**
 * INT-1390：报告中心/历史报告批量对比对 Benchmark 报告（发布时点快照，无 task 关联）
 * 后端必然「未找到关联的任务数据」。锁定：
 * 1. 选中集含 Benchmark 快照 / 无 task 关联报告时，批量对比按钮禁用（batchCompareDisabled）
 * 2. handleBatchCompare 前置拦截：不发 POST /reports/secondary-compare，改 warning toast 提示
 * 3. 可对比报告（task 带 taskId / comparison 家族）照常走 secondaryCompare
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  getAll: vi.fn(),
  secondaryCompare: vi.fn(),
  restore: vi.fn(),
  purge: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/composables/report/reportsPort', () => ({
  reportsPort: {
    getAll: mocks.getAll,
    secondaryCompare: mocks.secondaryCompare,
    batchDelete: vi.fn(),
    delete: vi.fn(),
    publish: vi.fn(),
  },
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal }),
}));

vi.mock('@/composables/modal/constants', () => ({
  MODAL_TYPES: {
    BASIC_CONFIRM: 'basicConfirm',
    DELETE_CONFIRM: 'deleteConfirm',
  },
}));

vi.mock('@/composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({
    algorithmOptions: { value: [] },
    loadAlgorithms: vi.fn(),
    getAlgorithmLabel: vi.fn(),
  }),
}));

vi.mock('@/utils/socket', () => ({
  default: { connect: vi.fn(), on: vi.fn(), off: vi.fn() },
}));

vi.mock('@/composables/favorite/useFavorites', () => ({
  useFavorites: () => ({
    favoriteOnly: { value: false },
    favoriteIds: { value: new Set<string>() },
    isFavorite: vi.fn(() => false),
    toggleFavorite: vi.fn(),
    loadFavorites: vi.fn(),
    restore: mocks.restore,
    purge: mocks.purge,
  }),
}));

import { useHistoryReports } from '../historyReports';

/** 构造列表报告项（Report 领域形状；taskId 缺失用 undefined 而非 null） */
function makeReport(partial: { id: number | string; name: string; type: string; taskId?: number | string | null }) {
  return {
    id: partial.id,
    name: partial.name,
    type: partial.type,
    taskId: partial.taskId ?? undefined,
    taskName: '',
    summary: { totalCases: 0 },
    status: 'published',
    createdAt: '2026-10-23T00:00:00Z',
    updatedAt: '2026-10-23T00:00:00Z',
  } as any;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getAll.mockResolvedValue({ items: [], total: 0 });
  mocks.secondaryCompare.mockResolvedValue({ status: 'completed' });
});

describe('INT-1390：batchCompareDisabled 禁用态（选中集含不可对比报告）', () => {
  it('选中 Benchmark 报告 → 禁用', () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: 'Benchmark 快照A', type: 'benchmark' }),
      makeReport({ id: 2, name: 'Benchmark 快照B', type: 'benchmark' }),
    ];
    ctx.selectedReports.value = new Set([1, 2]);

    expect(ctx.batchCompareDisabled.value).toBe(true);
  });

  it('选中含 Benchmark 的混合集 → 禁用', () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: 'Benchmark 快照A', type: 'benchmark' }),
      makeReport({ id: 2, name: '任务报告B', type: 'task', taskId: 100 }),
    ];
    ctx.selectedReports.value = new Set([1, 2]);

    expect(ctx.batchCompareDisabled.value).toBe(true);
  });

  it('选中非对比家族且无 taskId 的报告 → 禁用（后端亦无任务数据）', () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: '无任务草稿', type: 'task', taskId: null }),
      makeReport({ id: 2, name: '无任务草稿2', type: 'standard', taskId: null }),
    ];
    ctx.selectedReports.value = new Set([1, 2]);

    expect(ctx.batchCompareDisabled.value).toBe(true);
  });

  it('选中可对比报告（task 带 taskId / comparison 家族）→ 不禁用', () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: '任务报告A', type: 'task', taskId: 100 }),
      makeReport({ id: 2, name: '任务报告B', type: 'task', taskId: 200 }),
    ];
    ctx.selectedReports.value = new Set([1, 2]);
    expect(ctx.batchCompareDisabled.value).toBe(false);

    ctx.allReports.value = [
      makeReport({ id: 3, name: '对比报告A', type: 'comparison' }),
      makeReport({ id: 4, name: '二次对比B', type: 'secondary_comparison' }),
    ];
    ctx.selectedReports.value = new Set([3, 4]);
    expect(ctx.batchCompareDisabled.value).toBe(false);
  });
});

describe('INT-1390：handleBatchCompare 前置拦截（不发必然失败的后端请求）', () => {
  it('全为 Benchmark → warning toast 提示，不调 secondaryCompare', async () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: 'Benchmark 快照A', type: 'benchmark' }),
      makeReport({ id: 2, name: 'Benchmark 快照B', type: 'benchmark' }),
    ];
    ctx.selectedReports.value = new Set([1, 2]);

    await ctx.handleBatchCompare();

    expect(mocks.secondaryCompare).not.toHaveBeenCalled();
    expect(ctx.toast.value?.type).toBe('warning');
    expect(ctx.toast.value?.message).toContain('不支持对比');
    expect(ctx.toast.value?.message).toContain('Benchmark 快照A');
  });

  it('混合 Benchmark + 任务报告 → warning toast，不调 secondaryCompare', async () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: 'Benchmark 快照A', type: 'benchmark' }),
      makeReport({ id: 2, name: '任务报告B', type: 'task', taskId: 100 }),
    ];
    ctx.selectedReports.value = new Set([1, 2]);

    await ctx.handleBatchCompare();

    expect(mocks.secondaryCompare).not.toHaveBeenCalled();
    expect(ctx.toast.value?.type).toBe('warning');
  });

  it('可对比报告 → 正常调 secondaryCompare（非 generating 直接成功提示）', async () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: '任务报告A', type: 'task', taskId: 100 }),
      makeReport({ id: 2, name: '任务报告B', type: 'task', taskId: 200 }),
    ];
    ctx.selectedReports.value = new Set([1, 2]);

    await ctx.handleBatchCompare();

    expect(mocks.secondaryCompare).toHaveBeenCalledTimes(1);
    expect(mocks.secondaryCompare).toHaveBeenCalledWith([1, 2]);
    expect(ctx.toast.value?.type).toBe('success');
  });
});

describe('INT-1390 返工：跨页残留选中（选中项不在当前列表时判定仍基于选择时元数据快照）', () => {
  it('选中 Benchmark 后翻页（当前列表换为任务报告）→ 按钮仍禁用，handleBatchCompare 仍前置拦截', async () => {
    const ctx = useHistoryReports();
    // 第 1 页：两条 Benchmark，逐条勾选（选择时同步记录元数据快照）
    ctx.allReports.value = [
      makeReport({ id: 1, name: 'Benchmark 快照A', type: 'benchmark' }),
      makeReport({ id: 2, name: 'Benchmark 快照B', type: 'benchmark' }),
    ];
    ctx.toggleReportSelection(ctx.allReports.value[0], undefined);
    ctx.toggleReportSelection(ctx.allReports.value[1], undefined);
    expect(ctx.selectedReports.value.size).toBe(2);
    expect(ctx.batchCompareDisabled.value).toBe(true);

    // 翻到第 2 页：当前列表不含选中 id（跨页残留选中）
    ctx.allReports.value = [
      makeReport({ id: 3, name: '任务报告C', type: 'task', taskId: 300 }),
      makeReport({ id: 4, name: '任务报告D', type: 'task', taskId: 400 }),
    ];

    expect(ctx.batchCompareDisabled.value).toBe(true);

    await ctx.handleBatchCompare();
    expect(mocks.secondaryCompare).not.toHaveBeenCalled();
    expect(ctx.toast.value?.type).toBe('warning');
    expect(ctx.toast.value?.message).toContain('Benchmark 快照A');
  });

  it('跨页混合选中（1 个跨页 Benchmark + 1 个当前页任务报告）→ 按钮仍禁用', () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: 'Benchmark 快照A', type: 'benchmark' }),
    ];
    ctx.toggleReportSelection(ctx.allReports.value[0], undefined);

    // 翻页后勾选当前页任务报告
    ctx.allReports.value = [
      makeReport({ id: 3, name: '任务报告C', type: 'task', taskId: 300 }),
    ];
    ctx.toggleReportSelection(ctx.allReports.value[0], undefined);

    expect(ctx.selectedReports.value.size).toBe(2);
    expect(ctx.batchCompareDisabled.value).toBe(true);
  });

  it('跨页可选报告（均为 task 带 taskId）→ 按钮保持可用，照常走接口', async () => {
    const ctx = useHistoryReports();
    ctx.allReports.value = [
      makeReport({ id: 1, name: '任务报告A', type: 'task', taskId: 100 }),
      makeReport({ id: 2, name: '任务报告B', type: 'task', taskId: 200 }),
    ];
    ctx.toggleReportSelection(ctx.allReports.value[0], undefined);
    ctx.toggleReportSelection(ctx.allReports.value[1], undefined);

    ctx.allReports.value = [
      makeReport({ id: 3, name: '任务报告C', type: 'task', taskId: 300 }),
    ];
    expect(ctx.batchCompareDisabled.value).toBe(false);

    await ctx.handleBatchCompare();
    expect(mocks.secondaryCompare).toHaveBeenCalledTimes(1);
    expect(mocks.secondaryCompare).toHaveBeenCalledWith([1, 2]);
  });
});
