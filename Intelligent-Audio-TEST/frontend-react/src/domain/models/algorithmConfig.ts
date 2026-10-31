/**
 * 算法配置域领域模型（domain 层；17_配置运维.md §11 组件树落位）。
 * 形态对照 api_gateway/schemas/algorithm.py（_algorithm_definition_schemas.py /
 * _algorithm_group_schemas.py / _algorithm_param_schemas.py / _algorithm_api_param_schemas.py /
 * _algorithm_dimension_schemas.py）实测字段，snake_case 仅存在于 infrastructure 层，
 * 前端 Domain 一律 camelCase（基座规范 §10.1 字段命名契约）。
 */
import type { DeviceType } from './device'

export type AlgorithmStatus = 'online' | 'offline'

/** 算法侧设备参数（AlgorithmDeviceParamItem）；API 实例参数见 `domain/models/apiConfig` 的算法作用域行 */
export type DeviceApiParam = {
  id: number
  /** 设备级作用域：null = 算法类型级默认，非空 = 该设备覆盖 */
  deviceId?: number | null
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

/** 用例参数适用范围（与后端 `CaseParamScope` 同词表；⚠ 与 `param_profiles.scope` 是两回事） */
export type CaseParamScope = 'common' | DeviceType

/**
 * 用例参数适用范围取值（后端 `CaseParamScope` 词表：common + DeviceType 三值）。
 * types / zod schema / infrastructure DTO 归一都以此为唯一来源，禁止再写字面量数组。
 */
export const CASE_PARAM_SCOPES = [
  'common',
  'physical',
  'http_api',
  'websocket_api',
] as const satisfies readonly CaseParamScope[]

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
  /** 适用范围（common = 所有设备类型通用；其余为 DeviceType 值，只在对应设备类型的用例生效） */
  scope: CaseParamScope
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
  /** join / collect / first（V9.7.10/V9.7.31 Vue 实测 merge_mode 取值） */
  mergeMode: 'join' | 'collect' | 'first' | null
  helpText: string | null
}

/**
 * 参数来源（param_mappings.source：case/case_config/reference/device/api；设备/API 映射恒 case）。
 * 已知五值 + 未知字符串透传：存量脏数据（如 history source='evaluation'）读侧原样保留、
 * 写侧原样提交，避免读时丢弃 → 保存时把 DB 行重写（后端 upsert 自然键含 source）。
 */
export type MappingSource =
  | 'case'
  | 'case_config'
  | 'reference'
  | 'device'
  | 'api'
  | (string & {})

/** 转换类型（transform_type：none/uppercase/lowercase/json_parse/rttm_to_obj/stm_to_obj；API 映射另含 base64） */
export type MappingTransformType =
  | 'none'
  | 'uppercase'
  | 'lowercase'
  | 'json_parse'
  | 'rttm_to_obj'
  | 'stm_to_obj'
  | 'base64'

/**
 * 参数映射（ParamMappingItem）。
 * 读侧对齐 algorithm_service 序列化（_serialize_mappings）全字段：
 * id / source / source_param / source_direction / dimension_id / dimension_name /
 * target_param / transform_type；param_name/target_param_name 后端不下发时前端按 code 查参数表兜底。
 * 设备/API 映射：dimension_id 恒 null，target_param=目标参数代码；评估映射：dimension_id 必填，
 * target_param=维度内目标参数代码（空串表整维度映射，兼容存量 target_param=维度名形态）。
 */
export type ParamMapping = {
  id: number
  source: MappingSource | null
  /** 源参数方向（source_direction：input/output；缺省 output） */
  sourceDirection: string | null
  sourceParam: string
  /** 源参数名称（后端不下发时前端按 code 查参数表兜底） */
  paramName: string | null
  /** 目标评估维度 id（仅 evaluation 映射；设备/API 恒 null） */
  dimensionId: number | null
  /** 目标评估维度名 */
  dimensionName: string | null
  targetParam: string
  /** 目标参数名称（设备/API=目标参数名；评估=维度内参数名） */
  targetParamName: string | null
  transformType: MappingTransformType
}

/**
 * 映射按来源分组：device / evaluation。
 * 算法级 API 映射（`source=api`）已迁移到 API 实例作用域（策略 + 实例覆盖），
 * 由 `features/algorithm-config/param-profiles` 与 API 编辑弹窗维护。
 */
export type AlgorithmMappings = {
  device: ParamMapping[]
  evaluation: ParamMapping[]
}

/**
 * 评估维度参数（GET /algorithm/dimension-params/{dimension_id} 响应；
 * evaluation 映射「目标参数」下拉选项数据源）。
 * 序列化对照 algorithm_service config_cache._serialize_dimension_param。
 */
export type DimensionParam = {
  id: number
  dimensionId: number
  dimensionName: string | null
  /** 参数代码（evaluation 映射 target_param 存该值） */
  code: string
  name: string | null
  label: string | null
  fieldType: string | null
  required: boolean
  defaultValue: unknown
  helpText: string | null
  uiOrder: number | null
  passThreshold: number | null
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
  caseParams: CaseParam[]
  referenceParams: ReferenceParam[]
  mappings: AlgorithmMappings
  associatedDimensions: DimensionRelation[]
  /** 引用该算法的用例数（列表列「关联用例」；definitions 响应无计数字段时为 null，
   *  由 useAlgorithmCaseCounts 经 fetchCaseCountByAlgorithmType 异步补齐，见 INT-1319 P3-1） */
  caseCount: number | null
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
