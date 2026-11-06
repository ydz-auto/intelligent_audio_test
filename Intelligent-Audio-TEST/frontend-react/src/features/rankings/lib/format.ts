/**
 * 排行榜数字/日期格式化（interfaces 层，照 newAPI format.ts 思路：单位缩写等）。
 * 通用数字复用 Intl.NumberFormat 默认 locale（AGENTS.md §3.1：不传语言码）。
 */

/** 主值格式化：{metricValue}{unit}；≥1000 缩写（1.2K/3.4M，保留两位内） */
export function formatMetricValue(value: number, unit: string): string {
  return `${formatCompactNumber(value)}${unit}`
}

/** 通用紧凑数字（≥1000 → 1.2K/3.4M；其余保留两位内） */
export function formatCompactNumber(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) {
    return `${trimZeros((value / 1_000_000).toFixed(2))}M`
  }
  if (abs >= 1_000) {
    return `${trimZeros((value / 1_000).toFixed(2))}K`
  }
  return trimZeros(String(value))
}

function trimZeros(text: string): string {
  return text.replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
}

/** 基线差文案：±{|delta| 保留 2 位}{unit}；0 或空返回 null（渲染「—」） */
export function formatGap(
  value: number | null,
  unit: string
): string | null {
  if (value === null || value === 0) return null
  const sign = value > 0 ? '+' : '-'
  return `${sign}${Math.abs(value).toFixed(2)}${unit}`
}

/** 计算于角标：{YYYY-MM-DD HH:mm}（ISO 字符串 → 本地时间） */
export function formatComputedAt(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 组卡角标：{MM-DD HH:mm}（计算时刻短格式） */
export function formatComputedAtShort(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** score100 归一化分：有值「{X} 分」，空「—」 */
export function formatScore100(value: number | null): string {
  return value === null ? '—' : `${trimZeros(String(value))} 分`
}

/** 百分位（保留整数，越低越靠前） */
export function formatPercentile(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}%`
}

/** 名次计数「N/M」 */
export function formatRankCount(rank: number, total: number): string {
  return `${rank}/${total}`
}
