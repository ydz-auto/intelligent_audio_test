/**
 * 算法配置页 feature 类型（features/algorithm-config）。
 * 含 §6 算法编辑表单的 RHF 值类型（字段数组行以 key 唯一标识，删除/重排稳定）。
 */
import type {
  AlgorithmDefinition,
  AlgorithmGroup,
  CaseParamScope,
} from '@/domain/models/algorithmConfig'

/** 弹窗/抽屉统一状态（页级 Context Provider 语义，§3.1） */
export type MutateMode = 'create' | 'edit' | 'clone'

/** 统一参数表作用域（§6.4 作用域 chips：全部/设备/用例；行来源 device/case） */
export type ParamScope = 'all' | 'device' | 'case'

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

/** 设备参数行（§6 编辑表单；API 参数改由 API 实例作用域维护，算法侧不再承载） */
export type DeviceApiParamRow = {
  key: string
  paramCode: string
  paramName: string
  direction: 'input' | 'output'
  paramType: string
  required: boolean
  /** §6.4 默认值列恒显（设备参数亦支持 defaultValue） */
  defaultValue: string
  helpText: string
}

export type CaseParamRow = {
  key: string
  paramCode: string
  paramName: string
  paramType: string
  scope: CaseParamScope
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

/** 参数映射行（§6.5 设备/评估两节共用；评估行带 dimensionId/dimensionName） */
export type MappingRow = {
  key: string
  /** 后端映射主键（已入库行；新增行无 id，聚合提交后由后端分配） */
  id?: number
  /** 来源类型（设备恒 case；评估：case/case_config/reference/device） */
  source?: string
  /** 源参数方向（source_direction：input/output，缺省 output） */
  sourceDirection?: string
  sourceParam: string
  /** 源参数名称（读侧回填或按 code 查参数表兜底） */
  paramName?: string
  /** 目标评估维度 id（评估行；设备恒空） */
  dimensionId?: string
  /** 目标评估维度名（维度内目标参数的归属维度 / 分组展示键） */
  dimensionName?: string
  targetParam: string
  /** 目标参数名称（设备=目标参数名；评估=维度内参数名） */
  targetParamName?: string
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
  /** 乐观锁版本号（§6.2/§12-10；编辑态取发布版 revision，草稿/发布请求携带做条件更新） */
  revision?: number
  deviceParams: DeviceApiParamRow[]
  caseParams: CaseParamRow[]
  referenceParams: ReferenceParamRow[]
  mappings: {
    device: MappingRow[]
    evaluation: MappingRow[]
  }
  associatedDimensions: DimensionRow[]
}

/** 分组管理弹窗状态（§7.1） */
export type GroupManagerState = {
  open: boolean
  groups: AlgorithmGroup[]
}
