/**
 * 报告具体用例分组客户端聚合纯函数（15_报告域.md §3.3.7「用例卡片分组」INT-1034 同步，INT-1049 实施）。
 * 与 domain/lib/sub-view-aggregation.ts 同款约定：子组按用例数降序（同数按中文名升序稳定）、兜底桶置末尾；
 * 报告用例行自带 `category`/`tags`（ReportCaseItem），不新增后端请求——组内 CaseCard 照全站统一口径。
 * - groupReportCasesByCategory：按 category 建桶（单用例单分类单次呈现），无分类用例归「未分类」桶（末尾）。
 * - groupReportCasesByTag：按 tags 逐标签建桶（多标签用例在命中的每个标签子组各呈现一次），
 *   无标签用例归「未设置标签」桶（末尾）；色点/分类角标从报告标签登记表（reportTagRegistry）解析。
 * 报告用例无 duration 数据，组头不落「总时长」徽章（CaseSubGroup 的 totalDuration 语义不在报告侧使用）。
 */
import type { ReportCaseItem } from '@/domain/models/report'
import type { TagItem } from '@/domain/models/testTag'

/** 报告用例分组（只读组织行：组名 + 计数「{n} 个用例」；组头组件 ReportGroupHeader 消费） */
export interface ReportCaseSubGroup {
  /** 稳定 key（分类名/标签名；「未分类」/「未设置标签」桶用固定字符串） */
  key: string
  /** 组头文案（分类名/标签名/「未分类」/「未设置标签」） */
  label: string
  cases: ReportCaseItem[]
  /** 数据驱动色（仅按标签子组；未设置标签桶/按分组子组为 null） */
  color: string | null
  /** 分类名角标（仅按标签子组） */
  categoryName: string | null
}

const UNCATEGORIZED_BUCKET_KEY = '__uncategorized__'
const UNTAGGED_BUCKET_KEY = '__untagged__'
/** 后端 result_summary.category 对「无分组用例」的兜底哨兵（report_service 实测返回 "未分类"） */
const UNCATEGORIZED_LABEL = '未分类'

/**
 * 按分类客户端聚合（§3.3.7 按分组视图：组头=分类名+计数；无分类用例归「未分类」桶，末尾）。
 * 后端对无分组用例以哨兵 "未分类" 下发（result_summary.category），与空值同归兜底桶，
 * 避免把哨兵当真实组名（审计口径：兜底组末尾弱化）。
 */
export function groupReportCasesByCategory(
  cases: ReportCaseItem[]
): ReportCaseSubGroup[] {
  const buckets = new Map<string, ReportCaseSubGroup>()

  for (const c of cases) {
    const raw = c.category?.trim() ?? ''
    const isUncategorized =
      !raw || raw === UNCATEGORIZED_LABEL
    const key = isUncategorized
      ? UNCATEGORIZED_BUCKET_KEY
      : (c.category ?? UNCATEGORIZED_BUCKET_KEY)
    const existing = buckets.get(key)
    if (existing) {
      existing.cases.push(c)
    } else {
      buckets.set(key, {
        key,
        label: isUncategorized ? UNCATEGORIZED_LABEL : raw,
        cases: [c],
        color: null,
        categoryName: null,
      })
    }
  }

  const groups = [...buckets.values()]
  groups.sort(
    (a, b) =>
      b.cases.length - a.cases.length ||
      a.label.localeCompare(b.label, 'zh-CN')
  )

  const uncategorized = groups.filter((g) => g.key === UNCATEGORIZED_BUCKET_KEY)
  const rest = groups.filter((g) => g.key !== UNCATEGORIZED_BUCKET_KEY)
  return [...rest, ...uncategorized]
}

/**
 * 按标签客户端聚合（§3.3.7 按标签视图：组头=标签名+计数；无标签用例归「未设置标签」桶，末尾）。
 * 多标签用例在每个命中的标签子组各呈现一次；色点/分类角标从报告标签登记表解析。
 */
export function groupReportCasesByTag(
  cases: ReportCaseItem[],
  tagRegistry: TagItem[]
): ReportCaseSubGroup[] {
  const registry = new Map(tagRegistry.map((t) => [t.name, t]))
  const buckets = new Map<string, ReportCaseSubGroup>()

  for (const c of cases) {
    for (const tagName of c.tags) {
      const existing = buckets.get(tagName)
      if (existing) {
        existing.cases.push(c)
      } else {
        const tag = registry.get(tagName)
        buckets.set(tagName, {
          key: tagName,
          label: tagName,
          cases: [c],
          color: tag?.color ?? null,
          categoryName: tag?.categoryName ?? null,
        })
      }
    }
  }

  const groups = [...buckets.values()]
  groups.sort(
    (a, b) =>
      b.cases.length - a.cases.length ||
      a.label.localeCompare(b.label, 'zh-CN')
  )

  const untagged = cases.filter((c) => c.tags.length === 0)
  if (untagged.length > 0) {
    groups.push({
      key: UNTAGGED_BUCKET_KEY,
      label: '未设置标签',
      cases: untagged,
      color: null,
      categoryName: null,
    })
  }

  return groups
}
