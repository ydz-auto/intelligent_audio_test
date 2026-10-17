/**
 * 子视图客户端聚合纯函数（domain/lib 层，11_用例域.md §3.5/§3.6/§9）。
 * groupCasesByTag：分组卡内「按标签」子视图——对组内已加载用例按 tags 客户端聚合，
 *   多标签用例在命中的每个标签子组各呈现一次；无标签用例归入「未设置标签」桶（末尾）。
 * groupCasesByCaseGroup：标签卡内「按用例分组」子视图——对标签下已加载用例按 group_id/group_name
 *   客户端聚合（单用例单分组→单次呈现）；无分组用例归入「未分组」桶（末尾）。
 *   防御（审计 P3-2）：groupId 非空但 groupName 缺失时 label 以 groupId 兜底，
 *   避免与真「未分组」桶（key='__ungrouped__'）文案混淆。
 * 两条纯函数可单测；数据源均为列表 DTO 自带字段（TestCaseListItem.tags / groupId / groupName），
 * 不新增后端请求。
 */
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TagItem } from '@/domain/models/testTag'

/** 子分组（只读组织行：名称/计数/总时长；按标签子组带色点与分类角标） */
export interface CaseSubGroup {
  /** 稳定 key（标签名/分组 id；未设置标签/未分组桶用固定字符串） */
  key: string
  /** 子分组头文案（标签名/分组名/「未设置标签」/「未分组」） */
  label: string
  cases: TestCaseListItem[]
  /** 数据驱动色（仅按标签子组；未设置标签桶/按分组子组为 null） */
  color: string | null
  /** 分类名角标（仅按标签子组） */
  categoryName: string | null
  /** 子组总时长（秒；totalDuration 求和，展示「总时长 {x}」徽章） */
  totalDuration: number
}

const sumDuration = (cases: TestCaseListItem[]): number =>
  cases.reduce((sum, c) => sum + (c.totalDuration ?? 0), 0)

const UNTAGGED_BUCKET_KEY = '__untagged__'
const UNGROUPED_BUCKET_KEY = '__ungrouped__'

/**
 * 按标签客户端聚合（§3.5 按标签子视图）。
 * - 对已加载用例的 tags 逐标签建桶（多标签用例多次呈现）；
 * - 子组默认按用例数降序（同数按名称升序稳定）；
 * - 无标签用例归入「未设置标签」桶（末尾）。
 */
export function groupCasesByTag(
  cases: TestCaseListItem[],
  tagRegistry: TagItem[]
): CaseSubGroup[] {
  const registry = new Map(tagRegistry.map((t) => [t.name, t]))
  const buckets = new Map<string, CaseSubGroup>()

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
          totalDuration: 0,
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
      totalDuration: 0,
    })
  }

  for (const g of groups) g.totalDuration = sumDuration(g.cases)
  return groups
}

/**
 * 按用例分组客户端聚合（§3.6 按用例分组子视图）。
 * - 按 groupId/groupName 建桶（单用例单分组→单次呈现）；
 * - 子组默认按用例数降序（同数按名称升序稳定）；
 * - 无分组用例归入「未分组」桶（末尾）。
 */
export function groupCasesByCaseGroup(
  cases: TestCaseListItem[]
): CaseSubGroup[] {
  const buckets = new Map<string, CaseSubGroup>()

  for (const c of cases) {
    const key = c.groupId ?? UNGROUPED_BUCKET_KEY
    const existing = buckets.get(key)
    if (existing) {
      existing.cases.push(c)
    } else {
      buckets.set(key, {
        key,
        label: c.groupName ?? c.groupId ?? '未分组',
        cases: [c],
        color: null,
        categoryName: null,
        totalDuration: 0,
      })
    }
  }

  const groups = [...buckets.values()]
  groups.sort(
    (a, b) =>
      b.cases.length - a.cases.length ||
      a.label.localeCompare(b.label, 'zh-CN')
  )

  const ungrouped = groups.filter((g) => g.key === UNGROUPED_BUCKET_KEY)
  const rest = groups.filter((g) => g.key !== UNGROUPED_BUCKET_KEY)

  for (const g of [...rest, ...ungrouped]) g.totalDuration = sumDuration(g.cases)
  return [...rest, ...ungrouped]
}
