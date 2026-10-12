/**
 * INT-157 筛选交互对齐——回归测试
 * 覆盖三处修复的契约：
 * 1) ReportView「排序资源」端到端：helpers camelCase sortResource → reportsApi 归一 → DTO snake_case sort_resource
 * 2) HistoryReports 报告类型值域：一律使用后端原值 secondary_comparison（禁 camelCase secondaryComparison 回潮）
 * 3) createCaseDataHelpers 排序参数仅在「评估维度+指标」分支携带 sortResource
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

vi.mock('@/composables/report/reportsPort', () => ({
  reportsPort: { searchCases: vi.fn() },
}));
vi.mock('../../../infrastructure/http/client', () => ({
  request: vi.fn(),
  apiBaseUrl: 'http://localhost:5000/api/v1',
}));

import { reportsPort } from '@/composables/report/reportsPort';
import { request } from '../../../infrastructure/http/client';
import { createCaseDataHelpers } from '../specificCaseDataHelpers';
import { reportsApi } from '../../../infrastructure/api/reportsApi';
import { toReportSearchCasesDto } from '../../../infrastructure/adapters/report.dto';
import { REPORT_TABS, REPORT_TAB_OPTIONS } from '../../../views/HistoryReports/historyReports';

const mockedSearchCases = vi.mocked(reportsPort.searchCases);
const mockedRequest = vi.mocked(request);

function makeDeps(overrides: Record<string, any> = {}) {
  return {
    props: { reportData: { taskType: 'all' } },
    cases: ref([]),
    totalCases: ref(0),
    currentPage: ref(1),
    pageSize: ref(20),
    casesLoading: ref(false),
    casesLoadError: ref(''),
    searchKeyword: ref(''),
    selectedCategories: ref([]),
    selectedTags: ref([]),
    selectedMetrics: ref([]),
    sortDimension: ref('评估维度'),
    selectedSortMetric: ref('accuracy'),
    selectedSortResource: ref('device_1'),
    sortOrder: ref('desc'),
    processTags: (tags: any) => tags || [],
    ...overrides,
  };
}

beforeEach(() => {
  mockedSearchCases.mockReset();
  mockedRequest.mockReset();
  mockedSearchCases.mockResolvedValue({ items: [], total: 0 });
  mockedRequest.mockResolvedValue({ items: [], total: 0 });
});

describe('INT-157 ReportView 排序资源链路（helpers → api）', () => {
  it('评估维度+指标排序时 loadCasesPage 携带 sortResource', async () => {
    const h = createCaseDataHelpers(makeDeps());
    await h.loadCasesPage(5);
    const params = mockedSearchCases.mock.calls[0][1] as any;
    expect(params.sortBy).toBe('metric');
    expect(params.sortMetric).toBe('accuracy');
    expect(params.sortResource).toBe('device_1');
    expect(params.sortOrder).toBe('desc');
  });

  it('排序资源为空时 sortResource 归一为 undefined（不拼无效参数）', async () => {
    const h = createCaseDataHelpers(makeDeps({ selectedSortResource: ref('') }));
    await h.loadCasesPage(5);
    const params = mockedSearchCases.mock.calls[0][1] as any;
    expect(params.sortResource).toBeUndefined();
  });

  it('非评估维度排序不携带 sortResource / sortMetric', async () => {
    const h = createCaseDataHelpers(makeDeps({ sortDimension: ref('任务') }));
    await h.loadCasesPage(5);
    const params = mockedSearchCases.mock.calls[0][1] as any;
    expect(params.sortBy).toBe('任务');
    expect(params.sortResource).toBeUndefined();
    expect(params.sortMetric).toBeUndefined();
  });

  it('导出全量链路 loadAllCasesForExport 同样携带 sortResource', async () => {
    const h = createCaseDataHelpers(makeDeps());
    await h.loadAllCasesForExport(7);
    const params = mockedSearchCases.mock.calls[0][1] as any;
    expect(params.sortBy).toBe('metric');
    expect(params.sortResource).toBe('device_1');
  });

  it('reportsApi.searchCases 将 sortResource 归一进 POST 请求体 sort_resource', async () => {
    await reportsApi.searchCases(9, { sortBy: 'metric', sortMetric: 'accuracy', sortResource: 'device_1', sortOrder: 'asc' });
    const [, , body] = mockedRequest.mock.calls[0] as any[];
    expect(body).toMatchObject({ sort_by: 'metric', sort_metric: 'accuracy', sort_resource: 'device_1', sort_order: 'asc' });
  });

  it('reportsApi.searchCases 兼容旧 snake_case 入参双拼写', async () => {
    await reportsApi.searchCases(9, { sort_by: 'metric', sort_resource: 'api_2' });
    const [, , body] = mockedRequest.mock.calls[0] as any[];
    expect(body).toMatchObject({ sort_by: 'metric', sort_resource: 'api_2' });
  });

  it('toReportSearchCasesDto：sortResource → sort_resource；未传时不携带该键', () => {
    const withRes = toReportSearchCasesDto({ page: 1, perPage: 20, sortResource: 'device_1' });
    expect(withRes.sort_resource).toBe('device_1');
    const withoutRes = toReportSearchCasesDto({ page: 1, perPage: 20 });
    expect('sort_resource' in withoutRes).toBe(false);
  });
});

describe('INT-157 HistoryReports 报告类型值域对齐（后端原值）', () => {
  it('REPORT_TYPE_MAP 覆盖后端原值 secondary_comparison（红测锁定：当前缺失，卡片类型徽章显示英文原值）', async () => {
    const { REPORT_TYPE_MAP } = await import('../../../domain/constants/reportLabels');
    expect(REPORT_TYPE_MAP['secondary_comparison']).toBe('二次对比报告');
  });

  it('Tab 常量值为后端原值（all/draft/published/comparison）', () => {
    expect(Object.values(REPORT_TABS)).toEqual(['all', 'draft', 'published', 'comparison']);
    REPORT_TAB_OPTIONS.forEach(o => {
      expect(o.value).not.toContain('secondaryComparison');
    });
  });
});

describe('INT-157 打回修复 F1/F3：对比报告类型判定收敛 domain', () => {
  it('isComparisonReportType：后端原值 secondary_comparison 命中（F1 主场景：二次对比报告走对比面板与对比保存分支）', async () => {
    const { isComparisonReportType } = await import('../../../domain/model/report');
    expect(isComparisonReportType('secondary_comparison')).toBe(true);
  });

  it('isComparisonReportType：comparison 与历史遗留值兼容命中；task/standard/空值不命中（既有行为不回归）', async () => {
    const { isComparisonReportType } = await import('../../../domain/model/report');
    expect(isComparisonReportType('comparison')).toBe(true);
    expect(isComparisonReportType('secondaryComparison')).toBe(true);
    expect(isComparisonReportType('secondary')).toBe(true);
    expect(isComparisonReportType('task')).toBe(false);
    expect(isComparisonReportType('standard')).toBe(false);
    expect(isComparisonReportType(undefined)).toBe(false);
    expect(isComparisonReportType(null)).toBe(false);
    expect(isComparisonReportType('')).toBe(false);
  });

  it('isSecondaryComparisonReportType：secondary_comparison 命中二次家族（F3：标题「二次对比报告」）；comparison 不命中（标题「任务对比报告」）', async () => {
    const { isSecondaryComparisonReportType } = await import('../../../domain/model/report');
    expect(isSecondaryComparisonReportType('secondary_comparison')).toBe(true);
    expect(isSecondaryComparisonReportType('secondaryComparison')).toBe(true);
    expect(isSecondaryComparisonReportType('secondary')).toBe(true);
    expect(isSecondaryComparisonReportType('comparison')).toBe(false);
    expect(isSecondaryComparisonReportType('task')).toBe(false);
    expect(isSecondaryComparisonReportType(undefined)).toBe(false);
  });

  it('REPORT_TYPE_MAP 后端原值键与历史遗留键并存（卡片类型徽章新旧数据都显示中文）', async () => {
    const { REPORT_TYPE_MAP } = await import('../../../domain/constants/reportLabels');
    expect(REPORT_TYPE_MAP['secondary_comparison']).toBe('二次对比报告');
    expect(REPORT_TYPE_MAP['secondaryComparison']).toBe('二次对比报告');
    expect(REPORT_TYPE_MAP['secondary']).toBe('二次对比报告');
    expect(REPORT_TYPE_MAP['comparison']).toBe('对比报告');
    expect(REPORT_TYPE_MAP['task']).toBe('任务报告');
  });
});
