/**
 * BatchDimensionModal —— 常量配置
 */

/** 默认权重 */
export const DEFAULT_WEIGHT = 50

/** 默认阈值 */
export const DEFAULT_THRESHOLD = 60

/** 最后一轮的特殊标识（-1 代表动态解析的"最后一轮"） */
export const LAST_ROUND_NUMBER = -1

/** 轮次范围模式枚举 */
export const ROUND_MODE = {
  ALL: 'all',
  SPECIFIC: 'specific',
  PER_ROUND: 'per_round',
} as const
