/**
 * 用例管理页常量（features/testcases，11_用例域.md §8 中文文案全量源）。
 * 视图页签/白名单/算法标签映射/时长格式化；徽章映射走 status-badge 语义名。
 * INT-486 用例不分类型口径（负责人 2026-10-16）：用例无 api/e2e 之分，测试类型 facet
 * 与类型徽章移除；正式类型维度=算法类型（algorithmType，test_type 残留待 INT-79 废弃）。
 * INT-490 卡片流逆转：列显隐选项随表格版式废止，常量收敛为视图页签与格式化工具。
 */
export type TestCasesViewKey = 'by-group' | 'by-tag'

/**
 * 未分组虚拟组哨兵（唯一事实源；代码审计 P3-1 收敛——原 index 与 grouped-case-list 各写一遍）。
 * 契约：GET /testcases 的 group_id 为精确匹配、后端无该哨兵，故不携带 group_id 拉全量后
 * 前端按 groupId == null 过滤（infrastructure/api/testcases-api.ts fetchTestCases 同口径）。
 */
export const UNGROUPED_GROUP_ID = '__ungrouped__'

/** 视图页签（line 变体，§3.1）：按分组 / 按标签 */
export const TEST_CASES_TABS: Array<{ key: TestCasesViewKey; label: string }> = [
  { key: 'by-group', label: '按分组' },
  { key: 'by-tag', label: '按标签' },
]

export const TEST_CASES_TAB_WHITELIST: string[] = TEST_CASES_TABS.map(
  (t) => t.key
)

/**
 * 算法类型 id → 中文名（真实 GET /algorithm/options 的 value→name）。
 * 不内置本地假字典：调用方经 useAlgorithmLabelMap() 取真实映射传入，未取到原样回退 id。
 */
export function getAlgorithmLabel(
  algorithmType: string | null,
  labels?: Record<string, string>
): string {
  if (!algorithmType) return '—'
  return labels?.[algorithmType] ?? algorithmType
}

/** ISO 时间串 → 「YYYY-MM-DD HH:mm」（轻量格式化，无 dayjs；异常原样返回） */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}

/** 总时长（秒）→ 「{x}m {y}s」（§3.3；0/null 不显 —） */
export function formatCaseDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '—'
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rest = s % 60
  return rest === 0 ? `${m}m` : `${m}m ${rest}s`
}
