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
