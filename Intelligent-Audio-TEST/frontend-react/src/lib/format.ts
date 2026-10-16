/**
 * 数字格式化（照搬 newAPI lib/format.ts 同名函数语义，仅保留本卡消费项）。
 */

export function formatNumber(
  value: number | null | undefined,
  locales?: Intl.LocalesArgument
): string {
  if (value == null || Number.isNaN(value as number)) return '-'
  return Intl.NumberFormat(locales, { maximumFractionDigits: 2 }).format(
    value as number
  )
}
