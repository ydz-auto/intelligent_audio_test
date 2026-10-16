/**
 * 用例管理页常量（features/testcases，11_用例域.md §8 中文文案全量源）。
 * 视图页签/白名单/列显隐/算法标签映射/时长格式化；徽章映射走 status-badge 语义名。
 * INT-486 用例不分类型口径（负责人 2026-10-16）：用例无 api/e2e 之分，测试类型 facet
 * 与类型徽章移除；正式类型维度=算法类型（algorithmType，test_type 残留待 INT-79 废弃）。
 */
import { MOCK_ALGORITHMS } from '@/domain/models/algorithm'

export type TestCasesViewKey = 'by-group' | 'by-tag'

/** 视图页签（line 变体，§3.1）：按分组 / 按标签 */
export const TEST_CASES_TABS: Array<{ key: TestCasesViewKey; label: string }> = [
  { key: 'by-group', label: '按分组' },
  { key: 'by-tag', label: '按标签' },
]

export const TEST_CASES_TAB_WHITELIST: string[] = TEST_CASES_TABS.map(
  (t) => t.key
)

/** 算法类型 id → 中文名（useAlgorithmLabels 等价；数据源 MOCK_ALGORITHMS 登记表） */
export const ALGORITHM_LABELS: Record<string, string> = Object.fromEntries(
  MOCK_ALGORITHMS.map((a) => [a.id, a.name])
)

export function getAlgorithmLabel(algorithmType: string | null): string {
  if (!algorithmType) return '—'
  return ALGORITHM_LABELS[algorithmType] ?? algorithmType
}

/** 列显隐选项（视图选项下拉，§3.3；类型列已按口径收敛为算法类型列） */
export const COLUMN_OPTIONS = [
  { key: 'name', label: '用例名称' },
  { key: 'algorithm', label: '算法' },
  { key: 'tags', label: '标签' },
  { key: 'group', label: '分组' },
  { key: 'rounds', label: '轮次·时长' },
  { key: 'updatedAt', label: '更新时间' },
  { key: 'id', label: 'ID' },
] as const

export type CaseColumnKey = (typeof COLUMN_OPTIONS)[number]['key']

export const DEFAULT_VISIBLE_COLUMNS: CaseColumnKey[] = [
  'name',
  'algorithm',
  'tags',
  'rounds',
  'updatedAt',
]

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
