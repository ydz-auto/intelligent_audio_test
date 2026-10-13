/**
 * 冻结报告快照 → 报告页渲染视图模型（对齐 ReportView 构造的 report 对象结构）。
 *
 * INT-258：快照为 camelCase 冻结契约，本映射只做同形组装（无 case 转换）。
 * 关键约束：产出对象不带 id / taskId —— 报告页组件以二者判断走远程加载/回写
 * （searchCases / getCaseAveragesByFilters / scheduleSaveSummary），
 * 剥离后全部降级为本地冻结数据渲染，保证"不受源报告修改/删除影响"。
 */
import type { ReportSnapshot, ReportSnapshotCase } from '../../domain/model/publishedTask';

/** 报告页组件以 case.id 作为展开/钉选/详情 key；冻结行缺 id 时合成稳定 key（字符串） */
export type FrozenReportCase = Omit<ReportSnapshotCase, 'id'> & {
  id?: string | number;
};

export interface FrozenReportView {
  name: string;
  type: string;
  status: string;
  createdAt?: string | null;
  description?: string | null;
  conclusion: string;
  summary: Record<string, unknown>;
  cases: FrozenReportCase[];
}

/** 冻结快照 → 报告页视图模型（组件纯本地渲染，无远程请求、无回写） */
export function buildFrozenReportView(snapshot: ReportSnapshot): FrozenReportView {
  const cases: FrozenReportCase[] = (snapshot.cases || []).map((c, idx) => ({
    ...c,
    id: c.id ?? `${c.testCaseId ?? 'case'}-${idx}`,
  }));
  return {
    name: snapshot.name,
    type: snapshot.type || 'task',
    status: snapshot.status,
    createdAt: snapshot.createdAt,
    description: snapshot.description ?? '',
    conclusion: snapshot.analysis || '',
    summary: { ...(snapshot.summary || {}) } as Record<string, unknown>,
    cases,
  };
}
