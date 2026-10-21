/**
 * §6 编辑表单 领域模型 ↔ RHF 值转换（features/algorithm-config/mutate）。
 * 转换纯函数（便于单测）；克隆态载荷 type 追加 _copy、name 追加「(副本)」、剔除行级 id（INT-211 处置）。
 */
import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'
import type {
  AlgorithmFormValues,
  CaseParamRow,
  DeviceApiParamRow,
  DimensionRow,
  MappingRow,
  ReferenceParamRow,
} from '@/features/algorithm-config/types'
import type { SaveAlgorithmInput } from '@/infrastructure/api/algorithm-config-api'

let keyCounter = 0
function nextKey(prefix: string): string {
  keyCounter += 1
  return `${prefix}-${keyCounter}`
}

/** 领域模型 → 表单值（编辑/复制预填，§6.1） */
export function toFormValues(algorithm: AlgorithmDefinition): AlgorithmFormValues {
  return {
    type: algorithm.type,
    name: algorithm.name,
    groupId: algorithm.groupId != null ? String(algorithm.groupId) : '',
    displayOrder: algorithm.displayOrder,
    status: algorithm.status,
    description: algorithm.description ?? '',
    revision: algorithm.revision,
    deviceParams: algorithm.deviceParams.map<DeviceApiParamRow>((param) => ({
      key: nextKey('d'),
      paramCode: param.paramCode,
      paramName: param.paramName ?? '',
      direction: param.direction,
      paramType: param.paramType,
      required: param.required,
      defaultValue: param.defaultValue ?? '',
      helpText: param.helpText ?? '',
    })),
    apiParams: algorithm.apiParams.map<DeviceApiParamRow>((param) => ({
      key: nextKey('a'),
      paramCode: param.paramCode,
      paramName: param.paramName ?? '',
      direction: param.direction,
      paramType: param.paramType,
      required: param.required,
      defaultValue: param.defaultValue ?? '',
      helpText: param.helpText ?? '',
    })),
    caseParams: algorithm.caseParams.map<CaseParamRow>((param) => ({
      key: nextKey('c'),
      paramCode: param.paramCode,
      paramName: param.paramName ?? '',
      paramType: param.paramType,
      scope: param.scope,
      required: param.required,
      defaultValue: param.defaultValue ?? '',
      minValue: param.minValue != null ? String(param.minValue) : '',
      maxValue: param.maxValue != null ? String(param.maxValue) : '',
      step: param.step != null ? String(param.step) : '',
      unit: param.unit ?? '',
      annotationCode: param.annotationCode ?? '',
      fieldPath: param.fieldPath ?? '',
      helpText: param.helpText ?? '',
    })),
    referenceParams: algorithm.referenceParams.map<ReferenceParamRow>((param) => ({
      key: nextKey('r'),
      code: param.code,
      name: param.name,
      type: param.type,
      annotationCode: param.annotationCode ?? '',
      annotationFormat: param.annotationFormat ?? '',
      fieldPath: param.fieldPath ?? '',
      mergeMode: param.mergeMode ?? '',
      helpText: param.helpText ?? '',
    })),
    mappings: {
      device: algorithm.mappings.device.map<MappingRow>((mapping) => ({
        key: nextKey('md'),
        id: mapping.id,
        source: mapping.source ?? 'case',
        sourceDirection: mapping.sourceDirection ?? 'output',
        sourceParam: mapping.sourceParam,
        paramName: mapping.paramName ?? '',
        targetParam: mapping.targetParam,
        targetParamName: mapping.targetParamName ?? '',
        transformType: mapping.transformType,
      })),
      api: algorithm.mappings.api.map<MappingRow>((mapping) => ({
        key: nextKey('ma'),
        id: mapping.id,
        source: mapping.source ?? 'case',
        sourceDirection: mapping.sourceDirection ?? 'output',
        sourceParam: mapping.sourceParam,
        paramName: mapping.paramName ?? '',
        targetParam: mapping.targetParam,
        targetParamName: mapping.targetParamName ?? '',
        transformType: mapping.transformType,
      })),
      evaluation: algorithm.mappings.evaluation.map<MappingRow>((mapping) => ({
        key: nextKey('me'),
        id: mapping.id,
        source: mapping.source ?? 'case',
        sourceDirection: mapping.sourceDirection ?? 'output',
        sourceParam: mapping.sourceParam,
        paramName: mapping.paramName ?? '',
        dimensionId: mapping.dimensionId != null ? String(mapping.dimensionId) : '',
        dimensionName: mapping.dimensionName ?? '',
        targetParam: mapping.targetParam,
        targetParamName: mapping.targetParamName ?? '',
        transformType: mapping.transformType,
      })),
    },
    associatedDimensions: algorithm.associatedDimensions.map<DimensionRow>(
      (relation) => ({
        key: nextKey('dim'),
        dimensionId: String(relation.dimensionId),
        dimensionName: relation.dimensionName,
        weight: String(relation.weight),
        isDefault: relation.isDefault,
      })
    ),
  }
}

/** 空表单值（新建 create，§6.1：type/name 空、分组「请选择」、状态「上线」、displayOrder 0） */
export function emptyFormValues(): AlgorithmFormValues {
  return {
    type: '',
    name: '',
    groupId: '',
    displayOrder: 0,
    status: 'online',
    description: '',
    deviceParams: [],
    apiParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions: [],
  }
}

/** 克隆载荷（§7.4 复制：type 追加 _copy、name 追加「(副本)」） */
export function cloneFormValues(
  algorithm: AlgorithmDefinition
): AlgorithmFormValues {
  const values = toFormValues(algorithm)
  return {
    ...values,
    type: `${algorithm.type}_copy`,
    name: `${algorithm.name} (副本)`,
  }
}

/** 表单值 → 保存载荷（聚合提交 POST/PUT /algorithm/definitions，§6.3 落库口径） */
export function toSaveInput(values: AlgorithmFormValues): SaveAlgorithmInput {
  const strip = <T extends { key: string }>(rows: T[]): Array<Record<string, unknown>> =>
    rows.map(({ key: _key, ...rest }) => ({ ...rest }))

  return {
    type: values.type,
    name: values.name,
    groupId: values.groupId ? Number(values.groupId) : null,
    displayOrder: values.displayOrder,
    status: values.status,
    description: values.description,
    deviceParams: strip(values.deviceParams),
    apiParams: strip(values.apiParams),
    caseParams: strip(values.caseParams),
    referenceParams: strip(values.referenceParams),
    mappings: {
      device: strip(values.mappings.device),
      api: strip(values.mappings.api),
      evaluation: strip(values.mappings.evaluation),
    },
    associatedDimensions: strip(values.associatedDimensions),
  }
}

/** 供测试重置 key 计数器 */
export function __resetFormKeyCounter(): void {
  keyCounter = 0
}
