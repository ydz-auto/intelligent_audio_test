/**
 * 算法配置页 feature 类型（features/algorithm-config）。
 * 含 §6 算法编辑表单的 RHF 值类型（字段数组行以 key 唯一标识，删除/重排稳定）。
 */
import type {
  AlgorithmDefinition,
  AlgorithmGroup,
} from '@/domain/models/algorithmConfig'

/** 弹窗/抽屉统一状态（页级 Context Provider 语义，§3.1） */
export type MutateMode = 'create' | 'edit' | 'clone'

export type MutateSheetState = {
  open: boolean
  mode: MutateMode
  /** 编辑/复制预填源（create 为 null） */
  algorithm: AlgorithmDefinition | null
}

export type DetailDialogState = {
  open: boolean
  algorithm: AlgorithmDefinition | null
}

/** 确认弹窗状态（§7.4/7.5/7.7/7.8 族） */
export type AlgorithmConfirmState =
  | { kind: 'clone'; algorithm: AlgorithmDefinition }
  | { kind: 'delete'; algorithm: AlgorithmDefinition }
  | { kind: 'reload' }
  | { kind: 'bulk-delete'; types: string[]; count: number }
  | null

/* ───────────────────────── 编辑表单行类型（§6） ───────────────────────── */

export type DeviceApiParamRow = {
  key: string
  paramCode: string
  paramName: string
  direction: 'input' | 'output'
  paramType: string
  required: boolean
  helpText: string
}

export type CaseParamRow = {
  key: string
  paramCode: string
  paramName: string
  paramType: string
  scope: 'common' | 'api' | 'e2e'
  required: boolean
  defaultValue: string
  minValue: string
  maxValue: string
  step: string
  unit: string
  annotationCode: string
  fieldPath: string
  helpText: string
}

export type ReferenceParamRow = {
  key: string
  code: string
  name: string
  type: string
  annotationCode: string
  annotationFormat: string
  fieldPath: string
  mergeMode: string
  helpText: string
}

export type MappingRow = {
  key: string
  sourceParam: string
  targetParam: string
  transformType: string
}

export type DimensionRow = {
  key: string
  dimensionId: string
  dimensionName: string
  weight: string
  isDefault: boolean
}

/** §6 编辑表单聚合值类型 */
export type AlgorithmFormValues = {
  type: string
  name: string
  groupId: string
  displayOrder: number
  status: 'online' | 'offline'
  description: string
  deviceParams: DeviceApiParamRow[]
  apiParams: DeviceApiParamRow[]
  caseParams: CaseParamRow[]
  referenceParams: ReferenceParamRow[]
  mappings: {
    device: MappingRow[]
    api: MappingRow[]
    evaluation: MappingRow[]
  }
  associatedDimensions: DimensionRow[]
}

/** 分组管理弹窗状态（§7.1） */
export type GroupManagerState = {
  open: boolean
  groups: AlgorithmGroup[]
}
