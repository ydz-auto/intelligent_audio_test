/**
 * 冻结报告快照 → 报告页渲染视图模型（对齐 ReportView 构造的 report 对象结构）。
 *
 * INT-258：快照为 camelCase 冻结契约，本映射只做同形组装（无 case 转换）。
 * 关键约束：产出对象不带 id / taskId —— 报告页组件以二者判断走远程加载/回写
 * （searchCases / getCaseAveragesByFilters / scheduleSaveSummary），
 * 剥离后全部降级为本地冻结数据渲染，保证"不受源报告修改/删除影响"。
 *
 * INT-2023：旧版快照（schemaVersion=2 但后端尚未冻结 resources/resourceHeaders）
 * 里 summary 仍是报告聚合的原始形态——分组/标签为 [{id,name}] 对象数组、
 * deviceStats 为 snake_case、资源列只有 devices 对象。报告页组件消费的是
 * adapter 出口的 Domain 形状（分组为 name 字符串、资源键为 resources 字符串），
 * 直接透传会把对象渲染成 "[object Object]" / 原始 JSON。故在此把冻结 summary
 * 归一化为报告页 Domain 形状（与 reportAdapter.toReportSummary 出口一致），
 * 缺失的资源键/表头按 metricData 资源键 + 冻结 devices/apis 反推。
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

type Dict = Record<string, unknown>;

/** 普通对象判定（排除 null / 数组） */
function isPlainObject(value: unknown): value is Dict {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 分组 / 标签归一：后端可能冻结 [{id,name}] 对象数组，Domain 契约为 name 字符串数组 */
function toNameList(rows: unknown): string[] {
  if (!Array.isArray(rows)) return [];
  return rows
    .map((row) => {
      if (isPlainObject(row)) return String(row.name ?? '');
      return String(row ?? '');
    })
    .filter(Boolean);
}

/** 资源键：metricData 数组行取 resource；dict 形态（分类→资源→指标）取第二层键 */
function collectResourceKeys(metricData: unknown): string[] {
  const keys: string[] = [];
  const push = (value: unknown) => {
    const key = value === null || value === undefined ? '' : String(value);
    if (key && !keys.includes(key)) keys.push(key);
  };
  if (Array.isArray(metricData)) {
    metricData.forEach((row) => {
      if (isPlainObject(row)) push(row.resource);
    });
  } else if (isPlainObject(metricData)) {
    Object.values(metricData).forEach((categoryRows) => {
      if (isPlainObject(categoryRows)) Object.keys(categoryRows).forEach(push);
    });
  }
  return keys;
}

/** 资源键匹配冻结设备/API 引用（键形如 {id}-{name}[-{version}]） */
function matchResourceRef(key: string, refs: unknown[]): Dict | null {
  for (const ref of refs) {
    if (isPlainObject(ref)) {
      const id = ref.id;
      const name = ref.name;
      if (id !== null && id !== undefined && key.startsWith(`${id}-`)) return ref;
      if (name && key.includes(String(name))) return ref;
      continue;
    }
    if (typeof ref === 'string' && ref === key) return { name: ref };
  }
  return null;
}

/**
 * 反推资源表头（旧版快照缺 resourceHeaders）。
 * label 取冻结名称（如「pura90豆包」），并带上类型/系统等结构化字段供表头展示；
 * 匹配不到时回退资源键本身，保证不出现对象原文。
 */
function buildResourceHeaders(resourceKeys: string[], devices: unknown[], apis: unknown[]): Dict[] {
  return resourceKeys.map((key) => {
    const device = matchResourceRef(key, devices);
    const api = device ? null : matchResourceRef(key, apis);
    const ref = device ?? api;
    const name = ref ? String(ref.name ?? '') : '';
    const header: Dict = {
      key,
      label: name || key,
      type: device ? 'device' : api ? 'api' : undefined,
      id: ref?.id ?? null,
      name: name || null,
      editable: false,
    };
    if (device) {
      header.deviceType = device.type ?? null;
      header.system = device.system ?? null;
    }
    return header;
  });
}

/** 设备/API 统计归一：冻结形态为 snake_case（total_cases/...），报告页 Domain 为 camelCase */
function toResourceStat(raw: unknown): Dict {
  if (!isPlainObject(raw)) return {};
  const num = (value: unknown) => (value === null || value === undefined ? 0 : Number(value));
  return {
    ...raw,
    systemVersion: raw.systemVersion ?? raw.system_version ?? undefined,
    totalCases: raw.totalCases ?? num(raw.total_cases),
    completedCases: raw.completedCases ?? num(raw.completed_cases),
    failedCases: raw.failedCases ?? num(raw.failed_cases),
    successRate: raw.successRate ?? num(raw.success_rate),
  };
}

/** 冻结 summary 归一化为报告页 Domain 形状 */
function normalizeSummary(snapshot: ReportSnapshot): Dict {
  const summary: Dict = { ...(snapshot.summary || {}) };
  const devices = Array.isArray(summary.devices) ? summary.devices : [];
  const apis = Array.isArray(summary.apis) ? summary.apis : [];

  summary.caseCategories = toNameList(summary.caseCategories);
  summary.allCaseTags = toNameList(summary.allCaseTags);
  if (summary.allTags !== undefined) summary.allTags = toNameList(summary.allTags);

  const declaredResources = Array.isArray(summary.resources)
    ? summary.resources.map((item) => String(item ?? '')).filter(Boolean)
    : [];
  let resourceKeys = declaredResources.length > 0 ? declaredResources : collectResourceKeys(summary.metricData);
  if (resourceKeys.length === 0) resourceKeys = collectResourceKeys(summary.tagMetricData);
  summary.resources = resourceKeys;

  const declaredHeaders = Array.isArray(summary.resourceHeaders) ? summary.resourceHeaders : [];
  summary.resourceHeaders = declaredHeaders.length > 0
    ? declaredHeaders
    : buildResourceHeaders(resourceKeys, devices, apis);

  if (Array.isArray(summary.deviceStats)) summary.deviceStats = summary.deviceStats.map(toResourceStat);
  if (Array.isArray(summary.apiStats)) summary.apiStats = summary.apiStats.map(toResourceStat);

  return summary;
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
    summary: normalizeSummary(snapshot),
    cases,
  };
}
