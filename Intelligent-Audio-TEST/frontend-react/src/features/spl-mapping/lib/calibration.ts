/**
 * 数字域 RMS-SPL 校准点集校验/提交纯函数（features/spl-mapping/lib；§6.10 行级校验判据）。
 * P2 修复：提交 payload 过滤与 validCount 同源（行无错误 + 非重复 + 目标/增益非空），
 * 排除行级校验错误/重复/空值行，防空 targetSpl 序列化为 Number('')=0 落库（审计 P2）。
 */
import {
  CALIBRATION_TARGET_SPL_MAX,
  CALIBRATION_TARGET_SPL_MIN,
} from '@/features/spl-mapping/constants'
import { formatLinearGain } from '@/features/spl-mapping/lib/format'

/** 校准点集草稿行（表单字符串态） */
export interface CalibrationPointDraft {
  targetSpl: string
  gainLinear: string
  rmsDbfs: string
}

/** 行级校验错误（§6.10：SPL 范围/增益正数/限幅） */
export interface CalibrationPointError {
  targetSpl?: string
  gainLinear?: string
}

/** 提交 payload 行（§6.10 RmsSplCalibrateRequest 三元组 target_spl/gain_linear/rms_dbfs） */
export interface CalibrationPayloadPoint {
  targetSpl: number
  gainLinear: number
  rmsDbfs: number | null
}

/** 行级校验（§6.10：SPL 范围 0~120 / 增益正数 + min~max 限幅） */
export function validatePoint(
  point: CalibrationPointDraft,
  minGain: number,
  maxGain: number
): CalibrationPointError {
  const errors: CalibrationPointError = {}
  const target = Number(point.targetSpl)
  const gain = Number(point.gainLinear)
  if (point.targetSpl === '' || Number.isNaN(target)) {
    errors.targetSpl = '请输入目标 SPL'
  } else if (target < CALIBRATION_TARGET_SPL_MIN || target > CALIBRATION_TARGET_SPL_MAX) {
    errors.targetSpl = `范围 ${CALIBRATION_TARGET_SPL_MIN}~${CALIBRATION_TARGET_SPL_MAX}`
  }
  if (point.gainLinear === '' || Number.isNaN(gain) || gain <= 0) {
    errors.gainLinear = '请输入正数增益'
  } else if (gain < minGain || gain > maxGain) {
    errors.gainLinear = `限幅 ${formatLinearGain(minGain)}~${formatLinearGain(maxGain)}`
  }
  return errors
}

/** 重复目标 SPL 拦截（§6.10：重复 x 拦截；按数值判重，'65' 与 '65.0' 视为重复） */
export function detectDuplicateIndexes(points: CalibrationPointDraft[]): Set<number> {
  const seen = new Map<string, number[]>()
  points.forEach((point, index) => {
    const raw = point.targetSpl.trim()
    if (raw === '') return
    const numeric = Number(raw)
    if (Number.isNaN(numeric)) return
    const list = seen.get(String(numeric)) ?? []
    list.push(index)
    seen.set(String(numeric), list)
  })
  const duplicated = new Set<number>()
  seen.forEach((indexes) => {
    if (indexes.length > 1) indexes.forEach((i) => duplicated.add(i))
  })
  return duplicated
}

/** 有效行判据（§6.10：行无错误 + 非重复 + 目标/增益非空）——validCount 与 payload 同源 */
export function isValidCalibrationRow(
  point: CalibrationPointDraft,
  index: number,
  errors: CalibrationPointError[],
  duplicateIndexes: ReadonlySet<number>
): boolean {
  const hasError = Object.keys(errors[index] ?? {}).length > 0
  const isDuplicate = duplicateIndexes.has(index)
  return !hasError && !isDuplicate && point.targetSpl.trim() !== '' && point.gainLinear.trim() !== ''
}

/** 有效行计数（提交钮 disabled 门控：无有效点禁用） */
export function countValidCalibrationRows(
  points: CalibrationPointDraft[],
  errors: CalibrationPointError[],
  duplicateIndexes: ReadonlySet<number>
): number {
  return points.filter((point, index) =>
    isValidCalibrationRow(point, index, errors, duplicateIndexes)
  ).length
}

/** 提交 payload（§6.10 POST /digital-spl/{id}/calibrate；仅有效行，空 RMS 转 null） */
export function buildCalibrationPayload(
  points: CalibrationPointDraft[],
  errors: CalibrationPointError[],
  duplicateIndexes: ReadonlySet<number>
): CalibrationPayloadPoint[] {
  return points
    .filter((point, index) => isValidCalibrationRow(point, index, errors, duplicateIndexes))
    .map((point) => ({
      targetSpl: Number(point.targetSpl),
      gainLinear: Number(point.gainLinear),
      rmsDbfs:
        point.rmsDbfs === '' || Number.isNaN(Number(point.rmsDbfs))
          ? null
          : Number(point.rmsDbfs),
    }))
}
