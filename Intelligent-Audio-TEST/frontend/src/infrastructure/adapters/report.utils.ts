/**
 * Report Adapter —— 内部小工具
 *
 * ReportDto(snake_case) ⇄ Report(camelCase) 映射时复用的通用工具函数。
 * 本层为唯一知道 snake_case 的层，工具仅在此层使用。
 */

/** 安全字符串（null/undefined 回退默认值） */
export function s(value: unknown, fallback = ''): string {
  return value === null || value === undefined ? fallback : String(value)
}