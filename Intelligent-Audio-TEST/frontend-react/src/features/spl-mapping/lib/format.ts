/**
 * 声压级映射展示格式化（features/spl-mapping/lib；§4.2/4.3 列渲染纯函数）。
 * 默认 locale，不传语言码（AGENTS.md §3.1）。
 */

/** 线性增益 → dB（§4.3 gainToDb = 20log10；非正数/非有限回 '-'） */
export function gainToDb(gain: number | null | undefined): string {
  if (gain == null || !Number.isFinite(gain) || gain <= 0) return '-'
  return `${(20 * Math.log10(gain)).toFixed(1)} dB`
}

/** 时间格式化（mono tabular，YYYY-MM-DD HH:mm 口径） */
export function formatDateTime(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

/** 数字域参考基准列（§4.3：「{reference_spl} dB / {reference_gain_linear}」） */
export function formatReferenceBase(
  referenceSpl: number | null,
  referenceGainLinear: number | null
): string {
  if (referenceSpl == null && referenceGainLinear == null) return '—'
  return `${referenceSpl ?? '-'} dB / ${referenceGainLinear ?? '-'}`
}

/** 数字域增益限幅列（§4.3：「{min_gain_linear} ~ {max_gain_linear}」） */
export function formatGainClamp(
  minGainLinear: number | null,
  maxGainLinear: number | null
): string {
  if (minGainLinear == null && maxGainLinear == null) return '—'
  return `${minGainLinear ?? '-'} ~ ${maxGainLinear ?? '-'}`
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
