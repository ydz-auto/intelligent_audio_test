/**
 * INT-258：冻结报告快照 → 报告页视图模型组装单测。
 * 关键约束：产出对象不带 id/taskId（报告页组件降级本地渲染，无远程加载/回写）。
 */
import { describe, expect, it } from 'vitest';
import { buildFrozenReportView } from '../frozenReportView';
import type { ReportSnapshot } from '../../../domain/model/publishedTask';

function makeSnapshot(overrides: Partial<ReportSnapshot> = {}): ReportSnapshot {
  return {
    schemaVersion: 2,
    sourceReportId: 436,
    reportId: 436,
    name: '冻结报告',
    type: 'task',
    status: 'published',
    description: '说明',
    analysis: '整体通过',
    createdAt: '2026-10-13T10:00:00',
    summary: {
      totalCases: 10,
      completedCases: 9,
      failedCases: 1,
      passRate: 90,
      duration: 120,
      caseCategories: ['登录功能'],
      allCaseTags: ['回归'],
      allMetrics: [{ name: 'WER', unit: '%' }],
      dimensionValues: [{ name: 'WER', average_value: 7.2 }],
      devices: [{ id: 1, name: '测试手机' }],
      apis: [],
      deviceStats: [],
      apiStats: [],
      metricData: [{ resource: 'res-a', metrics: [{ metric: 'WER', value: 7.2 }] }],
      tagMetricData: [],
    },
    cases: [
      { id: 9001, testCaseId: 'tc-1', name: '登录用例', tags: [], metrics: {}, results: [], audios: [], referenceParams: {}, algorithmResults: {} },
      { testCaseId: 'tc-2', name: '播放用例', tags: [], metrics: {}, results: [], audios: [], referenceParams: {}, algorithmResults: {} },
    ],
    ...overrides,
  } as ReportSnapshot;
}

describe('buildFrozenReportView', () => {
  it('产出对象剥离 id/taskId（冻结视图禁止远程加载与回写）', () => {
    const view = buildFrozenReportView(makeSnapshot());
    expect(view).not.toHaveProperty('id');
    expect(view).not.toHaveProperty('taskId');
    expect(view.summary).not.toHaveProperty('reportId');
  });

  it('保留报告元数据与 summary 全字段透传', () => {
    const view = buildFrozenReportView(makeSnapshot());
    expect(view.name).toBe('冻结报告');
    expect(view.type).toBe('task');
    expect(view.conclusion).toBe('整体通过');
    expect(view.summary).toMatchObject({ totalCases: 10, passRate: 90 });
  });

  it('冻结用例保留原行 id；缺 id 的行合成稳定 key', () => {
    const view = buildFrozenReportView(makeSnapshot());
    expect(view.cases[0].id).toBe(9001);
    expect(view.cases[1].id).toBe('tc-2-1');
  });

  it('空 cases/缺 type 时安全兜底', () => {
    const view = buildFrozenReportView(makeSnapshot({ cases: [], type: null } as Partial<ReportSnapshot>));
    expect(view.cases).toEqual([]);
    expect(view.type).toBe('task');
  });
});

describe('buildFrozenReportView · INT-2023 旧快照 summary 归一化', () => {
  /** 旧版冻结快照：分组/标签为对象数组、deviceStats 为 snake_case、无 resources/resourceHeaders */
  function makeLegacySnapshot(): ReportSnapshot {
    const base = makeSnapshot();
    return {
      ...base,
      summary: {
        ...base.summary,
        caseCategories: [{ id: 'cat-1', name: '拒识' }, { id: 'cat-2', name: '环境理解' }],
        allCaseTags: [{ id: 97, name: '拒识' }],
        devices: [
          { id: 10, name: 'pura90豆包', type: 'phone', system: 'HarmonyOS', app_version: '1.0.0' },
        ],
        apis: [],
        deviceStats: [
          { id: 10, name: 'pura90豆包', status: 'online', metrics: { 环境理解评分: 3.21 }, total_cases: 188, completed_cases: 188, failed_cases: 0, success_rate: 100 },
        ],
        metricData: [
          { resource: '10-pura90豆包-1.0.0', metrics: [{ metric: '环境理解评分', value: 3.21 }] },
        ],
      },
    } as ReportSnapshot;
  }

  it('分组/标签对象数组归一为名称字符串（下拉与图表不再渲染 [object Object]）', () => {
    const view = buildFrozenReportView(makeLegacySnapshot());
    expect(view.summary.caseCategories).toEqual(['拒识', '环境理解']);
    expect(view.summary.allCaseTags).toEqual(['拒识']);
  });

  it('缺 resources/resourceHeaders 时按 metricData 资源键 + 冻结设备反推（名称 + 类型/系统）', () => {
    const view = buildFrozenReportView(makeLegacySnapshot());
    expect(view.summary.resources).toEqual(['10-pura90豆包-1.0.0']);
    expect(view.summary.resourceHeaders).toEqual([
      expect.objectContaining({
        key: '10-pura90豆包-1.0.0',
        label: 'pura90豆包',
        type: 'device',
        deviceType: 'phone',
        system: 'HarmonyOS',
      }),
    ]);
  });

  it('deviceStats snake_case 归一为 camelCase（总用例数/完成数/成功率不再是 0）', () => {
    const view = buildFrozenReportView(makeLegacySnapshot());
    expect(view.summary.deviceStats).toEqual([
      expect.objectContaining({ totalCases: 188, completedCases: 188, failedCases: 0, successRate: 100 }),
    ]);
  });

  it('已冻结 resources/resourceHeaders 时原样保留（不做二次反推）', () => {
    const base = makeSnapshot();
    const view = buildFrozenReportView({
      ...base,
      summary: {
        ...base.summary,
        resources: ['res-a'],
        resourceHeaders: [{ key: 'res-a', label: '资源 A' }],
      },
    } as ReportSnapshot);
    expect(view.summary.resources).toEqual(['res-a']);
    expect(view.summary.resourceHeaders).toEqual([{ key: 'res-a', label: '资源 A' }]);
  });
});
