/**
 * 标签管理页常量（features/tags，11_用例域.md §4.2/§5.4/§8 中文文案全量源）。
 * 色板 = 预设 8 色 + 自定义 color input（§5.4「预设色板 8 色 + 自定义」）；
 * 分类/标签色均走业务数据自带 color（数据驱动色，非主题色，§6 口径）。
 * 「未分类」固定尾项色点 #94a3b8（现 Vue TagManagement 实测口径）。
 */
export const TAG_PALETTE = [
  '#f97316', // 橙
  '#06b6d4', // 青
  '#8b5cf6', // 紫
  '#84cc16', // 黄绿
  '#14b8a6', // 青绿
  '#10b981', // 绿
  '#6366f1', // 靛
  '#ef4444', // 红
] as const

/** 未分类固定尾项色点（现实现口径） */
export const UNCATEGORIZED_COLOR = '#94a3b8'

/** 新建标签默认色（现 TagEditModal 实测默认） */
export const DEFAULT_TAG_COLOR = '#10b981'

/** 新建分类默认色（现 TagCategoryModal 实测默认） */
export const DEFAULT_CATEGORY_COLOR = '#6366f1'

/** 分类/标签名称最大长度（§5.4 maxlength 50） */
export const TAG_NAME_MAX_LENGTH = 50

/** 分类/标签描述最大长度（§5.4 maxlength 500） */
export const TAG_DESC_MAX_LENGTH = 500

/** 滚动分页触底阈值（px，现 category/tag scroll 语义 100px） */
export const SCROLL_LOAD_MORE_THRESHOLD = 100

/** 搜索防抖毫秒（§4.2：300ms） */
export const TAG_SEARCH_DEBOUNCE_MS = 300

/** 列表页首屏条数 + 滚动/「加载更多」追加步长（已显示 {n} / {总} 条 · 加载更多，§4.2） */
export const TAG_LIST_PAGE_SIZE = 20

/** ISO 时间串 → 「YYYY-MM-DD HH:mm」（轻量格式化，无 dayjs；异常原样返回） */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}
