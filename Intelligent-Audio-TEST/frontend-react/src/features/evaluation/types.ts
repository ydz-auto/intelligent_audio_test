/**
 * 评估维度页内部状态类型（features/evaluation）。
 * 弹窗/抽屉状态全部 props 化，页面装配组件持有并分派。
 */
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'

/** 维度表单抽屉状态（新增/编辑/复制预填；§5.5） */
export interface MutateDrawerState {
  open: boolean
  mode: 'create' | 'edit'
  dimension: Dimension | null
  /** 新增子维度预填：父维度 id + 分类 id（§4.1 行操作「添加子维度」） */
  presetParentId?: number | null
  presetCategoryId?: number | null
}

/** 分类表单弹窗状态（§5.5 分类表单） */
export interface CategoryDialogState {
  open: boolean
  category: EvaluationCategory | null
}

/** 规则试算弹窗状态（§4.1 行操作「规则试算」） */
export interface RuleCalcDialogState {
  open: boolean
  dimension: Dimension | null
}

/** API 健康测试结果弹窗状态（§5.5 行内「测试 API」） */
export interface HealthTestDialogState {
  open: boolean
  dimension: Dimension | null
}

/** 确认弹窗状态族（§5.6 + §4.1 批量/删除/分类删除） */
export type EvaluationConfirmState =
  | { kind: 'delete-dimension'; dimension: Dimension }
  | { kind: 'batch-action'; action: 'enable' | 'disable' | 'delete'; count: number }
  | { kind: 'delete-category'; category: EvaluationCategory }
  | { kind: 'duplicate-dimension'; dimension: Dimension }
