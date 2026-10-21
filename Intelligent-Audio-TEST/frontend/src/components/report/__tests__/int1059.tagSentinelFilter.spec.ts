/**
 * INT-1059 前端UX审计 P2：标签对比卡片「未标记/无标签」筛选哨兵归一化
 *
 * 点选「未标记/无标签」→ 请求体拆出哨兵（tags 剔除）+ includeUntagged=true；
 * 真实标签保留在 tags；二者并存时 tags 只含真实标签。
 * 对齐 CaseCategoryComparisonComponent 的 applyFilters 归一化口径。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/composables/report/reportsPort', () => ({
  reportsPort: { getCaseAveragesByFilters: vi.fn(), update: vi.fn() },
}));

import { reportsPort } from '@/composables/report/reportsPort';
import { useCaseTagComparison } from '../CaseTagComparisonComponent';

const mockedGet = vi.mocked(reportsPort.getCaseAveragesByFilters);

function makeReportData(overrides: Record<string, any> = {}) {
  return {
    id: 1001,
    taskId: 2001,
    summary: {
      allTags: ['标签A', '标签B'],
      allCaseTags: [],
      caseCategories: ['分组1'],
      resources: ['device_1'],
      allMetrics: [{ name: 'pass_rate', unit: '%' }],
    },
    ...overrides,
  };
}

/** getCaseAveragesByFilters 返回带 tagMetricData 的响应，让 reportId 分支命中后 return */
function makeTagMetricResponse() {
  return {
    tagMetricData: [
      { resource: 'device_1', tags: [{ tagName: '未标记', metrics: [{ metric: 'pass_rate', value: 50 }] }] },
    ],
  };
}

function flush() {
  return new Promise(r => setTimeout(r, 0));
}

beforeEach(() => {
  mockedGet.mockReset();
  mockedGet.mockResolvedValue(makeTagMetricResponse() as any);
});

describe('INT-1059 标签对比筛选哨兵归一化', () => {
  it('reportId 分支：点选「未标记」→ tags=[] + includeUntagged=true + asReportId=true', async () => {
    const c = useCaseTagComparison({ reportData: makeReportData() } as any);
    c.toggleTag('未标记');
    await flush();
    expect(mockedGet).toHaveBeenCalledTimes(1);
    const [reportId, filters, , asReportId] = mockedGet.mock.calls[0];
    expect(reportId).toBe(1001);
    expect(filters).toMatchObject({ tags: [], includeUntagged: true, categories: [] });
    expect(asReportId).toBe(true);
  });

  it('taskId 分支（无 report id）：点选「无标签」→ tags=[] + includeUntagged=true', async () => {
    const c = useCaseTagComparison({ reportData: makeReportData({ id: undefined }) } as any);
    c.toggleTag('无标签');
    await flush();
    expect(mockedGet).toHaveBeenCalledTimes(1);
    const [taskId, filters, , asReportId] = mockedGet.mock.calls[0];
    expect(taskId).toBe(2001);
    expect(filters).toMatchObject({ tags: [], includeUntagged: true, categories: [] });
    expect(asReportId).toBeUndefined();
  });

  it('真实标签不归一：tags=[\'标签A\'] + includeUntagged=false', async () => {
    const c = useCaseTagComparison({ reportData: makeReportData() } as any);
    c.toggleTag('标签A');
    await flush();
    const [, filters] = mockedGet.mock.calls[0];
    expect(filters).toMatchObject({ tags: ['标签A'], includeUntagged: false, categories: [] });
  });

  it('「未标记」+ 真实标签并存：tags 只含真实标签 + includeUntagged=true', async () => {
    const c = useCaseTagComparison({ reportData: makeReportData() } as any);
    c.toggleTag('未标记');
    c.toggleTag('标签A');
    await flush();
    // 第二次 applyFilters 反映两者并存的归一化结果
    const [, filters] = mockedGet.mock.calls[1];
    expect(filters).toMatchObject({ tags: ['标签A'], includeUntagged: true, categories: [] });
  });
});
