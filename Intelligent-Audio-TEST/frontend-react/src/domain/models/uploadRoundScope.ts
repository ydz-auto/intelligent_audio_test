/**
 * 上传选项轮次范围领域类型（§5.7 上传选项共用件；INT-1614）。
 * 两段各一套三档状态（评估维度 / 播放设备，互不联动）：所有轮次统一 / 指定轮次统一 / 逐轮设置。
 * 三档落值与 merge 载荷字段见 16_设备域.md §5.7.1 / §5.7.7。
 */

/** 轮次范围三档（§5.7.1 逐字文案：所有轮次（统一设置）/ 指定轮次（统一设置）/ 逐轮设置（每轮可不同）） */
export type UploadRoundScopeMode = 'all' | 'specific' | 'per_round'

/** 单段轮次范围状态（受控值；轮次数 N 由调用方按 §5.7.2 计算，不进本值） */
export interface UploadRoundScopeValue {
  mode: UploadRoundScopeMode
  /** 指定轮次档勾中的轮次号（1 基） */
  specificRounds: number[]
  /** 逐轮设置档当前编辑轮次（1 基） */
  activeRound: number
}

/** 逐轮取值（key = 轮次号，1 基；未出现的轮次 = 该轮未设置） */
export type UploadRoundValueMap<V> = Record<number, V>

/** 评估维度三档提交计划（§5.7.3 / §5.7.7；id 集，条目元数据在调用方目录里） */
export interface UploadDimensionPlan {
  mode: UploadRoundScopeMode
  /** all / specific 档的统一维度 id 集 */
  uniformIds: number[]
  /** specific 档勾中的轮次（1 基） */
  specificRounds: number[]
  /** per_round 档各轮维度 id 集（key = 轮次号；缺失 = 该轮不带评估维度） */
  perRoundIds: UploadRoundValueMap<number[]>
}

/** 播放设备三档提交计划（§5.7.4 / §5.7.7） */
export interface UploadDevicePlan {
  mode: UploadRoundScopeMode
  /** all / specific 档的统一设备 id */
  uniformId: number | null
  /** specific 档勾中的轮次（1 基） */
  specificRounds: number[]
  /** per_round 档各轮设备 id（key = 轮次号；缺失 = 该轮不写设备，保留 JSON 标注值 / 后端兜底） */
  perRoundIds: UploadRoundValueMap<number | null>
}

/** 初始轮次范围状态（所有轮次（统一设置）+ 第 1 轮） */
export function createUploadRoundScope(): UploadRoundScopeValue {
  return { mode: 'all', specificRounds: [1], activeRound: 1 }
}

/** 把轮次范围状态收敛到 [1, roundCount]（N 变小时丢弃越界勾选 / 当前轮） */
export function clampUploadRoundScope(
  value: UploadRoundScopeValue,
  roundCount: number
): UploadRoundScopeValue {
  const count = Math.max(1, roundCount)
  const specificRounds = value.specificRounds.filter((r) => r >= 1 && r <= count)
  const activeRound =
    value.activeRound >= 1 && value.activeRound <= count ? value.activeRound : 1
  if (
    specificRounds.length === value.specificRounds.length &&
    activeRound === value.activeRound
  ) {
    return value
  }
  return { ...value, specificRounds, activeRound }
}
