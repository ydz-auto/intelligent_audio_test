/**
 * 算法配置域领域模型（domain 层；17_配置运维.md §11 组件树落位）。
 * 形态对照 api_gateway/schemas/algorithm.py（_algorithm_definition_schemas.py /
 * _algorithm_group_schemas.py / _algorithm_param_schemas.py / _algorithm_api_param_schemas.py /
 * _algorithm_dimension_schemas.py）实测字段，snake_case 仅存在于 infrastructure 层，
 * 前端 Domain 一律 camelCase（基座规范 §10.1 字段命名契约）。
 */

export type AlgorithmStatus = 'online' | 'offline'

/** 设备参数（AlgorithmDeviceParamItem）——API 参数同契约（AlgorithmApiParamItem） */
export type DeviceApiParam = {
  id: number
  paramCode: string
  paramName: string | null
  label: string | null
  /** text / audio_stream / audio_file / text_file / rttm / stm / json */
  paramType: string
  /** input / output */
  direction: 'input' | 'output'
  required: boolean
  defaultValue: string | null
  helpText: string | null
  uiOrder: number
  hidden: boolean
}

/** 用例专属参数（CaseAlgorithmParamCreate） */
export type CaseParam = {
  id: number
  paramCode: string
  paramName: string | null
  label: string | null
  /** text / number / textarea / slider / switch / audio_select / device_select / json */
  paramType: string
  required: boolean
  defaultValue: string | null
  helpText: string | null
  uiOrder: number
  hidden: boolean
  /** common / api / e2e */
  scope: 'common' | 'api' | 'e2e'
  minValue: number | null
  maxValue: number | null
  step: number | null
  unit: string | null
  annotationCode: string | null
  fieldPath: string | null
}

/** 参考参数（ReferenceParamCreateRequest） */
export type ReferenceParam = {
  id: number
  code: string
  name: string
  /** text / audio / json / rttm / stm */
  type: string
  annotationCode: string | null
  annotationFormat: string | null
  fieldPath: string | null
  /** concat / collect / first */
  mergeMode: 'concat' | 'collect' | 'first' | null
  helpText: string | null
}

/** 参数映射（ParamMappingItem）；transformType none/uppercase/lowercase/json_parse（API 映射另含 base64） */
export type ParamMapping = {
  id: number
  sourceParam: string
  targetParam: string
  transformType: 'none' | 'uppercase' | 'lowercase' | 'json_parse' | 'base64'
}

/** 映射按来源分组：device / api / evaluation */
export type AlgorithmMappings = {
  device: ParamMapping[]
  api: ParamMapping[]
  evaluation: ParamMapping[]
}

/** 评估维度关联（AlgorithmDimensionRelationItem） */
export type DimensionRelation = {
  id: number
  dimensionId: number
  dimensionName: string
  weight: number
  isDefault: boolean
}

/** 算法定义（AlgorithmDetailResponse 子集 + 列表派生字段 caseCount） */
export type AlgorithmDefinition = {
  id: number
  /** 算法类型代码（主键，编辑态禁用） */
  type: string
  /** 显示名称 */
  name: string
  groupId: number | null
  groupName: string | null
  category: string | null
  description: string | null
  status: AlgorithmStatus
  icon: string | null
  displayOrder: number
  deviceParams: DeviceApiParam[]
  apiParams: DeviceApiParam[]
  caseParams: CaseParam[]
  referenceParams: ReferenceParam[]
  mappings: AlgorithmMappings
  associatedDimensions: DimensionRelation[]
  /** 引用该算法的用例数（列表列「关联用例」；definitions 响应无计数字段，mock 阶段按用例引用聚合语义补列） */
  caseCount: number
  /** 是否存在未发布草稿（INT-591 §3.4 可选列 Badge「有草稿」；后端 has_draft 字段返回后启用，未返回前不渲染） */
  hasDraft?: boolean
  /** 乐观锁版本号（INT-591 §6.2/§12-10；后端定义全量保存事务 RPC 带 revision，冲突 409 时刷新） */
  revision?: number
  createdAt: string
  updatedAt: string
}

/** 算法草稿（INT-591 §6.2 草稿模型；后端草稿 RPC 落定后平移，mock 阶段最小形态） */
export type AlgorithmDraft = {
  /** 算法类型代码（草稿归属；新建态草稿 type 可为空） */
  type: string
  /** 草稿乐观锁版本号（与发布版 revision 同语义） */
  revision: number
  /** 草稿最后保存时间（footer「上次保存 HH:mm:ss」） */
  savedAt: string
}

/** 算法分组（AlgorithmGroupItem） */
export type AlgorithmGroup = {
  id: number
  name: string
  description: string | null
  icon: string | null
  displayOrder: number
  algorithmCount: number
  createdAt: string
  updatedAt: string
}
