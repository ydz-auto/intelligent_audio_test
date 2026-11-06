/**
 * 声压级映射展示格式化（features/spl-mapping/lib；§4.2/4.3 列渲染纯函数）。
 * 默认 locale，不传语言码（AGENTS.md §3.1）。
 */

/** 线性增益 → dB（§4.3 gainToDb = 20log10；非正数/非有限回 '-'） */
export function gainToDb(gain: number | null | undefined): string {
  if (gain == null || !Number.isFinite(gain) || gain <= 0) return '-'
  return `${(20 * Math.log10(gain)).toFixed(1)} dB`
}

/**
 * 时间格式化（mono tabular，YYYY-MM-DD HH:mm 口径）。
 * INT-2211：后端下发裸 UTC，统一走共享工具按 UTC 解析后转本地展示。
 */
export { formatDateTime } from '@/lib/date-time'


/** 线性增益列值格式化：整数补一位小数（1.0/10.0），其余保留至 3 位去尾零（0.001/3.162）。 */
export function formatLinearGain(value: number): string {
  const s = value.toFixed(3).replace(/\.?0+$/, '')
  return s.includes('.') ? s : `${s}.0`
}

/** 数字域参考基准列（§4.3：「{reference_spl} dB / {reference_gain_linear}」） */
export function formatReferenceBase(
  referenceSpl: number | null,
  referenceGainLinear: number | null
): string {
  if (referenceSpl == null && referenceGainLinear == null) return '—'
  return `${referenceSpl ?? '-'} dB / ${referenceGainLinear == null ? '-' : formatLinearGain(referenceGainLinear)}`
}

/** 数字域增益限幅列（§4.3：「{min_gain_linear} ~ {max_gain_linear}」） */
export function formatGainClamp(
  minGainLinear: number | null,
  maxGainLinear: number | null
): string {
  if (minGainLinear == null && maxGainLinear == null) return '—'
  const min = minGainLinear == null ? '-' : formatLinearGain(minGainLinear)
  const max = maxGainLinear == null ? '-' : formatLinearGain(maxGainLinear)
  return `${min} ~ ${max}`
}

/** 物理域测量距离列（§4.2：「{distance} 米」） */
export function formatDistance(distance: number | null): string {
  if (distance == null) return '—'
  return `${distance} 米`
}

/** 物理域目标声压级列（§4.2：「{target_spl} dB」） */
export function formatTargetSpl(targetSpl: number | null): string {
  if (targetSpl == null) return '—'
  return `${targetSpl} dB`
}

/** 测试频率列（§4.2：「{test_frequency} Hz」） */
export function formatTestFrequency(frequency: number | null): string {
  if (frequency == null) return '—'
  return `${frequency} Hz`
}
