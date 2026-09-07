/**
 * BatchDimensionModal —— 类型定义
 *
 * 展示用维度标签、权重/阈值配置、确认提交载荷与组件 Props/Emits 契约。
 * 对外接口（props/emits）与拆分前保持一致，消费方零改动。
 */

/** 展示用维度标签（与 Domain 的 Dimension 区分，仅保留 id/name/description） */
export interface DimensionTag {
  id: string
  name: string
  description?: string
}

/** 单维度的权重与阈值配置 */
export interface DimConfig {
  weight: number
  threshold: number
}

/** 确认提交的单条维度（含权重与阈值） */
export interface DimensionConfigItem {
  id: string
  name: string
  weight: number
  threshold: number
}

/** 轮次范围模式（所有轮次 / 指定轮次 / 逐轮设置） */
export type RoundMode = 'all' | 'specific' | 'per_round'

/** 确认提交的整体载荷 */
export interface ConfirmData {
  dimensions: DimensionConfigItem[]
  testType: string
  roundMode: string
  roundNumbers: number[]
  roundDimensions?: Record<number, DimensionConfigItem[]>
  multiDimensions?: DimensionConfigItem[]
}

export interface Props {
  modalId: string
  title?: string
  caseCount?: number
  algorithmType?: string
  testType?: string
  maxRoundNumbers?: number
  selectionMode?: string
}

export interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: ConfirmData): void
  (e: 'cancel'): void
}
