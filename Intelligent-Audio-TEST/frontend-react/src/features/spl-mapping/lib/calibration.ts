/**
 * 数字域 RMS-SPL 校准点集校验/提交纯函数（features/spl-mapping/lib；§6.10 行级校验判据）。
 * INT-2081 口径调整：校准点主输入 = 目标 SPL + 实测 dBFS（必填 -120~0），
 * 线性增益为只读推导值（gain_linear = 10^((dBFS - 基础电平)/20)，基础电平 -30 dBFS，
 * 与物理域最终电平同源），不再作为用户入参校验；提交 payload 与 validCount 同源
 * （行无错误 + 非重复 + 目标/dBFS 非空），排除行级校验错误/重复/空值行，
 * 防空 targetSpl 序列化为 Number('')=0 落库（审计 P2）。
 */
import {
  CALIBRATION_RMS_MAX,
  CALIBRATION_RMS_MIN,
  CALIBRATION_TARGET_SPL_MAX,
  CALIBRATION_TARGET_SPL_MIN,
} from '@/features/spl-mapping/constants'
import { CALIBRATION_BASE_LEVEL_DBFS } from '@/domain/models/splMapping'

/** 校准点集草稿行（表单字符串态；增益由 dBFS 推导，不入草稿） */
export interface CalibrationPointDraft {
  targetSpl: string
  /** 实测 RMS（dBFS，必填 -120~0；主输入） */
  rmsDbfs: string
}

/** 行级校验错误（INT-2081：SPL 范围 / dBFS 必填与范围） */
export interface CalibrationPointError {
  targetSpl?: string
  rmsDbfs?: string
}

/** 提交 payload 行（§6.10 RmsSplCalibrateRequest 三元组 target_spl/gain_linear/rms_dbfs） */
export interface CalibrationPayloadPoint {
  targetSpl: number
  gainLinear: number
  rmsDbfs: number
}

/** 线性增益推导（INT-2081：gain_linear = 10^((dBFS - 基础电平)/20)，基础电平 -30 dBFS） */
export function deriveGainLinear(dbfs: string): number | null {
  const value = Number(dbfs)
  if (dbfs === '' || !Number.isFinite(value)) return null
  return Math.pow(10, (value - CALIBRATION_BASE_LEVEL_DBFS) / 20)
}

/** 按参考生成点集（INT-2081：以 refSpl 为中心 ±20dB 每 10dB 一点=5 点，按 dBFS 口径生成：
 *  增益 = refGain × 10^(offset/20)，再由 dBFS = 20log10(增益) + 基础电平反推 dBFS 主输入） */
export function generateCalibrationPointsByReference(
  refSpl: number,
  refGain: number
): CalibrationPointDraft[] {
  return [-20, -10, 0, 10, 20].map((offset) => {
    const target = Math.round((refSpl + offset) * 10) / 10
    const gain = refGain * Math.pow(10, offset / 20)
    const dbfs = 20 * Math.log10(gain) + CALIBRATION_BASE_LEVEL_DBFS
    return {
      targetSpl: String(target),
      rmsDbfs: dbfs.toFixed(1),
    }
  })
}

/** 行级校验（INT-2081：SPL 范围 0~120 / dBFS 必填 -120~0；增益为推导值不入参校验） */
export function validatePoint(point: CalibrationPointDraft): CalibrationPointError {
  const errors: CalibrationPointError = {}
  const target = Number(point.targetSpl)
  if (point.targetSpl === '' || Number.isNaN(target)) {
    errors.targetSpl = '请输入目标 SPL'
  } else if (target < CALIBRATION_TARGET_SPL_MIN || target > CALIBRATION_TARGET_SPL_MAX) {
    errors.targetSpl = `范围 ${CALIBRATION_TARGET_SPL_MIN}~${CALIBRATION_TARGET_SPL_MAX}`
  }
  const dbfs = Number(point.rmsDbfs)
  if (point.rmsDbfs === '' || Number.isNaN(dbfs)) {
    errors.rmsDbfs = '请输入实测 dBFS'
  } else if (dbfs < CALIBRATION_RMS_MIN || dbfs > CALIBRATION_RMS_MAX) {
    errors.rmsDbfs = `范围 ${CALIBRATION_RMS_MIN}~${CALIBRATION_RMS_MAX}`
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

/** 有效行判据（INT-2081：行无错误 + 非重复 + 目标/dBFS 非空）——validCount 与 payload 同源 */
export function isValidCalibrationRow(
  point: CalibrationPointDraft,
  index: number,
  errors: CalibrationPointError[],
  duplicateIndexes: ReadonlySet<number>
): boolean {
  const hasError = Object.keys(errors[index] ?? {}).length > 0
  const isDuplicate = duplicateIndexes.has(index)
  return !hasError && !isDuplicate && point.targetSpl.trim() !== '' && point.rmsDbfs.trim() !== ''
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

/** 提交 payload（INT-2081：POST /digital-spl/{id}/calibrate；仅有效行，增益由 dBFS 推导） */
export function buildCalibrationPayload(
  points: CalibrationPointDraft[],
  errors: CalibrationPointError[],
  duplicateIndexes: ReadonlySet<number>
): CalibrationPayloadPoint[] {
  return points
    .filter((point, index) => isValidCalibrationRow(point, index, errors, duplicateIndexes))
    .map((point) => ({
      targetSpl: Number(point.targetSpl),
      gainLinear: deriveGainLinear(point.rmsDbfs) ?? 0,
      rmsDbfs: Number(point.rmsDbfs),
    }))
}
