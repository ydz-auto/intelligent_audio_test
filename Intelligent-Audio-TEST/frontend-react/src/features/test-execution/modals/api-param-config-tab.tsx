/**
 * API 编辑弹窗「参数配置」页签（Presentation；T4.2）。
 *
 * 语义：API 实例作用域 + 可复用参数策略。
 * - 已绑定策略下拉：数据源 = 本 algorithm_type 下 scope=api 的策略；
 *   切换即 `PUT /algorithm/api-scope/{api_id}/binding`（未绑定 = 解绑）；
 * - 另存为新策略：`POST /algorithm/param-profiles`（以当前行整份创建），成功后绑定新 id；
 * - 克隆当前策略：`POST /algorithm/param-profiles/{id}/clone`，成功后绑定新 id；
 * - 输出字段 / 映射可增删改，保存 = `PUT /algorithm/api-scope/{api_id}/overrides`
 *   （body：algorithm_type / api_params / mappings；只覆盖本 API，不碰策略行）。
 *
 * 降级：
 * - 缺 `algorithm:read`（403）→ 页签「无权查看」；
 * - 新建 API（无 id）→ 字段与映射可直接编辑，草稿经 onDraftChange 上抛，
 *   随 API 创建一起提交；策略绑定 / 另存 / 克隆需先有 id，保持禁用；
 * - 未选择算法类型 → 下拉与保存禁用并提示。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  paramConfigQueryKeys,
  useApiParamConfig,
  useDimensionParams,
  useParamProfileOptions,
} from '@/application/test-execution/useApiParamConfig'
import type { AlgorithmApiMapping, AlgorithmApiParam } from '@/domain/models/apiConfig'
import type { DerivedFields } from '@/features/test-execution/modals/api-edit-dialog-model'
import {
  PARAM_DIRECTION_LABEL,
  PARAM_DIRECTIONS,
  PARAM_MAPPING_SOURCE_LABEL,
  PARAM_PROFILE_MAPPING_SOURCES,
  PARAM_TRANSFORM_TYPE_LABEL,
  PARAM_TRANSFORM_TYPES,
  PARAM_TYPE_LABEL,
  PARAM_TYPES,
  isParamProfileMappingSource,
  type ApiScopeOverridesInput,
  type ParamDirection,
  type ParamProfile,
  type ParamProfileInput,
  type ParamProfileMappingDraft,
  type ParamProfileMappingSource,
  type ParamProfileParamDraft,
  type ParamTransformType,
} from '@/domain/models/paramProfile'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  bindApiProfile,
  cloneProfile,
  createProfile,
  saveApiScopeOverrides,
} from '@/infrastructure/api/param-profile-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'

/** base-ui Select 不接受空串，未绑定用哨兵值 */
const UNBOUND = '__unbound__'
/** 输入映射的目标字段未选时的哨兵值 */
const UNSET = '__unset__'

const PARAM_TYPE_OPTIONS = PARAM_TYPES.map((value) => ({
  value,
  label: PARAM_TYPE_LABEL[value],
}))

/**
 * 参数类型下拉选项：枚举值 + 存量里枚举外的当前值（如 number）。
 * 不补这一项，界面会在保存时把该值收敛成 text（INT-2281）。
 */
function paramTypeOptionsOf(value: string) {
  if (!value || PARAM_TYPE_OPTIONS.some((item) => item.value === value)) {
    return PARAM_TYPE_OPTIONS
  }
  return [...PARAM_TYPE_OPTIONS, { value, label: `${value}（当前值）` }]
}

const TRANSFORM_TYPE_OPTIONS = PARAM_TRANSFORM_TYPES.map((value) => ({
  value,
  label: PARAM_TRANSFORM_TYPE_LABEL[value],
}))

/** 映射来源（api = API 输出 / case = 用例参数 / device = 设备输出） */
const MAPPING_SOURCE_OPTIONS = PARAM_PROFILE_MAPPING_SOURCES.map((value) => ({
  value,
  label: PARAM_MAPPING_SOURCE_LABEL[value],
}))

const MAPPING_DIRECTION_OPTIONS = PARAM_DIRECTIONS.map((value) => ({
  value,
  label: PARAM_DIRECTION_LABEL[value],
}))

interface EditableParamRow {
  key: number
  paramCode: string
  paramName: string
  /** 读侧原值；可能是枚举外的存量类型（如 number），保存时原样回写（INT-2281） */
  paramType: string
  required: boolean
  defaultValue: string
  helpText: string
  hidden: boolean
  /** 界面无编辑控件，保存时按读到的原值透传（INT-2281：整份同步会清空未提交列） */
  label: string | null
  validationRules: string | null
  uiOrder: string
  fieldPath: string
}

interface EditableMappingRow {
  key: number
  source: ParamProfileMappingSource
  sourceDirection: ParamDirection
  sourceParam: string
  targetParam: string
  dimensionId: string
  transformType: ParamTransformType
}

interface EditableInputMappingRow {
  key: number
  source: ParamProfileMappingSource
  sourceDirection: ParamDirection
  sourceParam: string
  targetParam: string
  transformType: ParamTransformType
}

/** 读侧映射来源：未知 / 空值收敛为 api（写侧后端缺省值同口径） */
function mappingSourceOf(mapping: AlgorithmApiMapping): ParamProfileMappingSource {
  return isParamProfileMappingSource(mapping.source) ? mapping.source : 'api'
}

/** 读侧源方向：空值按 output 处理（写侧后端缺省值同口径） */
function mappingDirectionOf(mapping: AlgorithmApiMapping): ParamDirection {
  return mapping.sourceDirection === 'input' ? 'input' : 'output'
}

/** 字段行归一：比较脏 / 透传共用一份口径，避免两处漂移 */
function paramSignatureOf(param: {
  paramCode: string
  paramType: string
  required: boolean
  defaultValue: string | null
  helpText: string | null
  hidden: boolean
  label: string | null
  validationRules?: string | null
  uiOrder: number | string
}) {
  return [
    param.paramCode,
    param.paramType,
    Number(param.uiOrder) || 0,
    param.required,
    param.defaultValue,
    param.helpText,
    param.hidden,
    param.label,
    param.validationRules ?? null,
  ]
}

function paramRowOf(param: AlgorithmApiParam, key: number): EditableParamRow {
  return {
    key,
    paramCode: param.paramCode,
    paramName: param.paramName ?? '',
    paramType: param.paramType || 'text',
    required: param.required,
    defaultValue: param.defaultValue ?? '',
    helpText: param.helpText ?? '',
    hidden: param.hidden,
    label: param.label,
    validationRules: param.validationRules ?? null,
    uiOrder: String(param.uiOrder ?? 0),
    fieldPath: param.fieldPath ?? '',
  }
}

function mappingRowOf(mapping: AlgorithmApiMapping, key: number): EditableMappingRow {
  return {
    key,
    source: mappingSourceOf(mapping),
    sourceDirection: mappingDirectionOf(mapping),
    sourceParam: mapping.sourceParam,
    targetParam: mapping.targetParam,
    dimensionId: mapping.dimensionId == null ? '' : String(mapping.dimensionId),
    transformType: PARAM_TRANSFORM_TYPES.includes(mapping.transformType as ParamTransformType)
      ? (mapping.transformType as ParamTransformType)
      : 'none',
  }
}

function inputMappingRowOf(mapping: AlgorithmApiMapping, key: number): EditableInputMappingRow {
  return {
    key,
    source: mappingSourceOf(mapping),
    sourceDirection: mappingDirectionOf(mapping),
    sourceParam: mapping.sourceParam,
    targetParam: mapping.targetParam,
    transformType: PARAM_TRANSFORM_TYPES.includes(mapping.transformType as ParamTransformType)
      ? (mapping.transformType as ParamTransformType)
      : 'none',
  }
}

/** 页面不展示的映射行：原值透传（否则整份同步会把它们软删） */
function passthroughMappingDraftOf(mapping: AlgorithmApiMapping): ParamProfileMappingDraft {
  return {
    source: mappingSourceOf(mapping),
    sourceDirection: mappingDirectionOf(mapping),
    sourceParam: mapping.sourceParam,
    targetParam: mapping.targetParam,
    dimensionId: mapping.dimensionId,
    transformType: PARAM_TRANSFORM_TYPES.includes(mapping.transformType as ParamTransformType)
      ? (mapping.transformType as ParamTransformType)
      : 'none',
  }
}

function draftInputMappingsOf(rows: EditableInputMappingRow[]): ParamProfileMappingDraft[] {
  return rows
    .filter((row) => row.sourceParam.trim() && row.targetParam.trim())
    .map((row) => ({
      source: row.source,
      sourceDirection: row.sourceDirection,
      sourceParam: row.sourceParam.trim(),
      targetParam: row.targetParam.trim(),
      dimensionId: null,
      transformType: row.transformType,
    }))
}

/** 服务端字段行按参数代码索引（整份保存时取未展示字段的原值） */
function originMapOf(params: AlgorithmApiParam[]): Map<string, AlgorithmApiParam> {
  return new Map(params.map((param) => [param.paramCode, param]))
}

/**
 * 文本列（默认值 / 帮助提示）：用户没改时按读侧原样回写（保留 null 与空串的差异），
 * 改过之后空串按 null 提交。不用常量兜底（INT-2281）。
 */
function textFieldOf(value: string, origin: string | null | undefined): string | null {
  if (value === (origin ?? '')) return origin ?? null
  return value.trim() === '' ? null : value
}

/**
 * 输出字段行 → 提交草稿。
 *
 * `required / defaultValue / helpText / hidden` 表格可见可改，按行内值提交
 * （INT-2281 回显口径）；`label / validationRules` 没有编辑控件，按读侧原值透传——
 * `PUT /algorithm/api-scope/{id}/overrides` 是整份保存，缺省即被清空（INT-2270）。
 */
function draftParamsOf(
  rows: EditableParamRow[],
  originals: Map<string, AlgorithmApiParam>
): ParamProfileParamDraft[] {
  return rows
    .filter((row) => row.paramCode.trim())
    .map((row) => {
      const paramCode = row.paramCode.trim()
      const origin = originals.get(paramCode)
      return {
        paramCode,
        paramName: row.paramName.trim() || null,
        paramType: row.paramType || 'text',
        direction: 'output',
        required: row.required,
        defaultValue: textFieldOf(row.defaultValue, origin?.defaultValue),
        helpText: textFieldOf(row.helpText, origin?.helpText),
        uiOrder: Number(row.uiOrder) || 0,
        hidden: row.hidden,
        fieldPath: row.fieldPath.trim() || null,
        // 无编辑控件的列按读侧原值透传（INT-2281）
        label: origin?.label ?? null,
        validationRules: origin?.validationRules ?? null,
      }
    })
}

/**
 * 输入字段（本页签只作输入映射的目标候选，不展示编辑控件）→ 提交草稿。
 *
 * 覆盖行按 (param_code, direction) 整份同步：不提交 input 行 = 保存时把它们软删。
 */
function draftInputParamsOf(params: AlgorithmApiParam[]): ParamProfileParamDraft[] {
  return params
    .filter((param) => param.paramCode.trim())
    .map((param) => ({
      paramCode: param.paramCode.trim(),
      paramName: param.paramName,
      paramType: param.paramType || 'text',
      direction: 'input',
      required: param.required,
      defaultValue: param.defaultValue,
      helpText: param.helpText,
      uiOrder: Number(param.uiOrder) || 0,
      hidden: param.hidden,
      fieldPath: param.fieldPath,
      label: param.label ?? null,
      validationRules: param.validationRules ?? null,
    }))
}

function draftMappingsOf(rows: EditableMappingRow[]): ParamProfileMappingDraft[] {
  return rows
    .filter((row) => row.sourceParam.trim() && row.targetParam.trim())
    .map((row) => ({
      source: row.source,
      sourceDirection: row.sourceDirection,
      sourceParam: row.sourceParam.trim(),
      targetParam: row.targetParam.trim(),
      dimensionId: row.dimensionId.trim() === '' ? null : Number(row.dimensionId),
      transformType: row.transformType,
    }))
}

/** 后端 message 优先（ApiError.userMessage 已按服务端文案收敛） */
function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage
  return error instanceof Error && error.message ? error.message : '操作失败，请重试'
}

/** 映射行「目标参数」下拉：候选随所选评估维度联动；存量值不在候选里时补一项。 */
function TargetParamSelect({
  dimensionId,
  value,
  disabled,
  onChange,
}: {
  dimensionId: number | null
  value: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  const paramsQuery = useDimensionParams(dimensionId)
  const options = useMemo(() => {
    const list = (paramsQuery.data ?? []).map((param) => ({
      value: param.code,
      label: param.name ? `${param.code}（${param.name}）` : param.code,
    }))
    if (value && !list.some((item) => item.value === value)) {
      list.unshift({ value, label: `${value}（当前值，不在该维度参数里）` })
    }
    return list
  }, [paramsQuery.data, value])

  if (dimensionId == null) {
    return <p className='text-muted-foreground text-xs'>先选目标维度</p>
  }
  if (paramsQuery.isLoading) {
    return (
      <span className='text-muted-foreground flex items-center gap-1 text-xs'>
        <Spinner className='size-3' />
        读取中
      </span>
    )
  }
  if (options.length === 0) {
    return <p className='text-muted-foreground text-xs'>该维度没有参数</p>
  }
  return (
    <Select
      value={value || UNSET}
      items={[{ value: UNSET, label: '未选择' }, ...options]}
      onValueChange={(next) => onChange(!next || next === UNSET ? '' : next)}
      disabled={disabled}
    >
      <SelectTrigger size='sm' className='w-40' aria-label='目标参数'>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={UNSET}>未选择</SelectItem>
        {options.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

interface ApiParamConfigTabProps {
  /** API 实例 id；新建 API（未保存）为 null */
  apiId: number | null
  /** 关联算法类型（apis.algorithm_type） */
  algorithmType: string
  /** `algorithm:param_manage` */
  canEdit: boolean
  /** 未保存改动上报：本页签有独立保存钮，弹窗底部「保存」不会落这些改动 */
  onDirtyChange?: (dirty: boolean) => void
  /** 草稿上报（新建态用：API 创建成功后由调用方连同覆盖行一起提交） */
  onDraftChange?: (draft: Omit<ApiScopeOverridesInput, 'algorithmType'>) => void
  /** 从请求模板 / 响应解析自动推导的字段（未手工声明时展示） */
  derived?: DerivedFields
}

export function ApiParamConfigTab({
  apiId,
  algorithmType,
  canEdit,
  onDirtyChange,
  onDraftChange,
  derived,
}: ApiParamConfigTabProps) {
  const queryClient = useQueryClient()
  // 读侧一律按 API 实例作用域取（新建态没有 id → 不发请求，只用内存草稿）
  const hasApiScope = apiId != null && Boolean(algorithmType)
  const config = useApiParamConfig(apiId, algorithmType, hasApiScope)
  const profiles = useParamProfileOptions(algorithmType, hasApiScope, apiId)
  /** 服务端输出行（按参数代码索引）：整份保存时透传界面未展示的字段 */
  const outputOriginals = useMemo(
    () => originMapOf(config.outputParams),
    [config.outputParams]
  )

  const [outputRows, setOutputRows] = useState<EditableParamRow[]>([])
  const [mappingRows, setMappingRows] = useState<EditableMappingRow[]>([])
  const [inputMappingRows, setInputMappingRows] = useState<EditableInputMappingRow[]>([])
  const [boundProfileId, setBoundProfileId] = useState<number | null>(null)
  const [nameDialog, setNameDialog] = useState<'create' | 'clone' | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftDescription, setDraftDescription] = useState('')
  const rowKeyRef = useRef(0)
  const appliedSignatureRef = useRef('')
  /** 上次已同步的服务端绑定值（null 与「未初始化」区分） */
  const lastServerBoundRef = useRef<number | null | undefined>(undefined)

  // 新建态（无 id）也允许编辑字段与映射：只改内存草稿，随 API 创建一起提交
  const editable = canEdit && Boolean(algorithmType)
  /** 依赖服务端 API 实例的动作（绑定 / 另存 / 克隆 / 立即保存）需先有 id */
  const persisted = apiId != null
  const canPersist = editable && persisted
  /**
   * 读侧就绪才允许整份保存：加载 / 失败时 outputRows、mappingRows 是空数组，
   * 此时提交等于用空集覆盖，会把该 API 的覆盖行全部软删（INT-2270）。
   */
  const configReady = config.state === 'ready'

  // 策略列表回读出本 API 的绑定 → 下拉回显；服务端值变化才同步，避免覆盖本地绑定结果
  const boundProfileIdFromServer = profiles.boundProfileId
  useEffect(() => {
    if (lastServerBoundRef.current === boundProfileIdFromServer) return
    lastServerBoundRef.current = boundProfileIdFromServer
    setBoundProfileId(boundProfileIdFromServer)
  }, [boundProfileIdFromServer])

  // 读侧数据到达 / 保存后重新拉取 → 同步到可编辑行；用户正在编辑时不覆盖。
  // 签名含「整份提交」的全部列（INT-2281）：只改必填 / 默认值 / 帮助提示 / 隐藏、
  // 或只改映射来源 / 方向，也必须被认作脏，否则界面会说「无改动」。
  const signature = useMemo(
    () =>
      JSON.stringify({
        params: config.outputParams.map((row) => paramSignatureOf(row)),
        mappings: config.mappings.map((row) => [
          mappingSourceOf(row),
          mappingDirectionOf(row),
          row.sourceParam,
          row.targetParam,
          row.dimensionId,
          row.transformType,
        ]),
        inputMappings: config.inputMappings.map((row) => [
          mappingSourceOf(row),
          mappingDirectionOf(row),
          row.sourceParam,
          row.targetParam,
          row.transformType,
        ]),
      }),
    [config.outputParams, config.mappings, config.inputMappings]
  )

  useEffect(() => {
    if (config.state !== 'ready') return
    if (signature === appliedSignatureRef.current) return
    appliedSignatureRef.current = signature
    setOutputRows(
      config.outputParams.map((param) => paramRowOf(param, rowKeyRef.current++))
    )
    setMappingRows(
      config.mappings.map((mapping) => mappingRowOf(mapping, rowKeyRef.current++))
    )
    setInputMappingRows(
      config.inputMappings.map((mapping) => inputMappingRowOf(mapping, rowKeyRef.current++))
    )
  }, [
    config.state,
    config.outputParams,
    config.mappings,
    config.inputMappings,
    signature,
  ])

  // 未保存改动判定：草稿行与服务端权威行逐字段比对（同一归一化口径）。
  // 保存成功 → 读侧失效重拉 → appliedSignatureRef 与草稿一致 → 自动回到 false。
  const dirty = useMemo(() => {
    if (config.state !== 'ready') return false
    return (
      JSON.stringify({
        params: outputRows.map((row) => paramSignatureOf(row)),
        mappings: mappingRows.map((row) => [
          row.source,
          row.sourceDirection,
          row.sourceParam,
          row.targetParam,
          row.dimensionId.trim() === '' ? null : Number(row.dimensionId),
          row.transformType,
        ]),
        inputMappings: inputMappingRows.map((row) => [
          row.source,
          row.sourceDirection,
          row.sourceParam,
          row.targetParam,
          row.transformType,
        ]),
      }) !== appliedSignatureRef.current
    )
  }, [config.state, outputRows, mappingRows, inputMappingRows])

  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])

  // 两个编辑器都不展示的映射行（source=device / case+output / 来源未知）：
  // 整份同步下不提交即被软删，所以每次提交都按读侧原值带上（INT-2281）
  const passthroughMappingDrafts = useMemo(
    () => config.otherMappings.map(passthroughMappingDraftOf),
    [config.otherMappings]
  )

  // 草稿上抛（新建态由弹窗在创建成功后统一提交，避免用户先保存再回来配参数）
  useEffect(() => {
    onDraftChange?.({
      params: [
        ...draftParamsOf(outputRows, outputOriginals),
        ...draftInputParamsOf(config.inputParams),
      ],
      mappings: [
        ...draftMappingsOf(mappingRows),
        ...draftInputMappingsOf(inputMappingRows),
        ...passthroughMappingDrafts,
      ],
    })
  }, [
    outputRows,
    outputOriginals,
    config.inputParams,
    mappingRows,
    inputMappingRows,
    passthroughMappingDrafts,
    onDraftChange,
  ])

  // 映射行「源参数」下拉候选 = 本 API 的输出字段；存量值已不在声明里时补一项，
  // 避免打开就丢值。
  const outputParamOptions = useMemo(() => {
    const options = config.outputParams.map((param) => ({
      value: param.paramCode,
      label: param.paramName
        ? `${param.paramCode}（${param.paramName}）`
        : param.paramCode,
    }))
    for (const row of mappingRows) {
      const code = row.sourceParam.trim()
      if (code && !options.some((item) => item.value === code)) {
        options.push({ value: code, label: `${code}（当前值，已不在声明中）` })
      }
    }
    return options
  }, [config.outputParams, mappingRows])

  // 输入映射目标候选 = 已声明输入字段 ∪ 请求模板里识别到的占位符（后者标注「自动」）
  const inputTargetOptions = useMemo(() => {
    const options = config.inputParams.map((param) => ({
      value: param.paramCode,
      label: param.paramName
        ? `${param.paramCode}（${param.paramName}）`
        : param.paramCode,
    }))
    for (const code of derived?.input ?? []) {
      if (!options.some((item) => item.value === code)) {
        options.push({ value: code, label: `${code}（自动识别）` })
      }
    }
    return options
  }, [config.inputParams, derived?.input])

  const invalidateScope = () => {
    void queryClient.invalidateQueries({
      queryKey: paramConfigQueryKeys.scopeParams(algorithmType, apiId),
    })
    void queryClient.invalidateQueries({
      queryKey: paramConfigQueryKeys.scopeMappings(algorithmType, apiId),
    })
  }

  const invalidateProfiles = () => {
    void queryClient.invalidateQueries({
      queryKey: paramConfigQueryKeys.profiles(algorithmType),
    })
  }

  const bindMutation = useMutation({
    mutationFn: (profileId: number | null) => {
      if (apiId == null) throw new Error('API 尚未保存')
      return bindApiProfile(apiId, profileId)
    },
    onSuccess: (result) => {
      setBoundProfileId(result.profileId)
      toast.success(result.profileId == null ? '已解绑策略' : '策略绑定已保存')
      invalidateScope()
      // 失效策略列表：下次重开弹窗按服务端回读，保证绑定后回读一致
      invalidateProfiles()
    },
    onError: (error) => {
      toast.error(errorMessage(error))
    },
  })

  const createMutation = useMutation({
    mutationFn: (input: { name: string; description: string | null }) => {
      const payload: ParamProfileInput = {
        scope: 'api',
        algorithmType,
        name: input.name,
        description: input.description,
        status: 'online',
        params: [
          ...draftParamsOf(outputRows, outputOriginals),
          ...draftInputParamsOf(config.inputParams),
        ],
        mappings: [
          ...draftMappingsOf(mappingRows),
          ...draftInputMappingsOf(inputMappingRows),
        ],
      }
      return createProfile(payload)
    },
    onSuccess: (profile) => {
      toast.success('新策略已创建')
      setNameDialog(null)
      invalidateProfiles()
      bindMutation.mutate(profile.id)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const cloneMutation = useMutation({
    mutationFn: (input: { name: string; description: string | null }) => {
      if (boundProfileId == null) throw new Error('当前未绑定策略')
      return cloneProfile(boundProfileId, input)
    },
    onSuccess: (profile) => {
      toast.success('策略已克隆')
      setNameDialog(null)
      invalidateProfiles()
      bindMutation.mutate(profile.id)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (apiId == null) throw new Error('API 尚未保存')
      return saveApiScopeOverrides(apiId, {
        algorithmType,
        // 整份保存：output 行 + input 声明行一起提交，未提交的既有覆盖行会被软删（INT-2270）
        params: [
          ...draftParamsOf(outputRows, outputOriginals),
          ...draftInputParamsOf(config.inputParams),
        ],
        mappings: [
          ...draftMappingsOf(mappingRows),
          ...draftInputMappingsOf(inputMappingRows),
          ...passthroughMappingDrafts,
        ],
      })
    },
    onSuccess: (result) => {
      toast.success(
        `参数配置已保存（新增 ${result.paramsCreated + result.mappingsCreated}，` +
          `更新 ${result.paramsUpdated + result.mappingsUpdated}，` +
          `删除 ${result.paramsDeleted + result.mappingsDeleted}）`
      )
      invalidateScope()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const updateOutputRow = (key: number, patch: Partial<EditableParamRow>) => {
    setOutputRows((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const updateMappingRow = (key: number, patch: Partial<EditableMappingRow>) => {
    setMappingRows((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const openNameDialog = (mode: 'create' | 'clone') => {
    setDraftName('')
    setDraftDescription('')
    setNameDialog(mode)
  }

  const nameDialogPending = createMutation.isPending || cloneMutation.isPending
  const submitNameDialog = () => {
    const name = draftName.trim()
    if (!name) {
      toast.error('请填写策略名称')
      return
    }
    const payload = { name, description: draftDescription.trim() || null }
    if (nameDialog === 'create') createMutation.mutate(payload)
    else if (nameDialog === 'clone') cloneMutation.mutate(payload)
  }

  if (config.state === 'forbidden') {
    return (
      <Empty className='border-border/60 border'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <Badge variant='secondary'>403</Badge>
          </EmptyMedia>
          <EmptyTitle>无权查看参数配置</EmptyTitle>
          <EmptyDescription>
            当前账号缺少 algorithm:read 权限，本页签不可用；不影响其它页签保存。
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const profilesForSelect: Array<{ value: string; label: string }> = [
    { value: UNBOUND, label: '未绑定' },
    ...(profiles.profiles as ParamProfile[]).map((profile) => ({
      value: String(profile.id),
      label: profile.name,
    })),
  ]

  return (
    <div className='min-w-0 space-y-3'>
      <p className='text-muted-foreground text-xs'>
        本页维护这个被测 API 的「输入映射（用例参数 → API 输入字段）+ 输出字段 + 输出映射
        （API 输出 → 评估参数）」，可绑策略继承默认值；新建 API 也可直接在这里配置。
      </p>

      {/* 自动识别字段：请求模板占位符 = 输入，响应解析路径 = 输出（无需手工声明也能看到） */}
      {((derived?.input.length ?? 0) > 0 || (derived?.output.length ?? 0) > 0) && (
        <div className='bg-muted/40 space-y-1 rounded-lg border p-2.5 text-xs'>
          <p className='font-medium'>自动识别字段</p>
          {(derived?.input.length ?? 0) > 0 && (
            <p className='text-muted-foreground'>
              输入（请求模板占位符）：{derived?.input.join('、')}
            </p>
          )}
          {(derived?.output.length ?? 0) > 0 && (
            <p className='text-muted-foreground'>
              输出（响应解析路径）：
              {derived?.output.map((row) => `${row.code} ← ${row.path}`).join('；')}
            </p>
          )}
        </div>
      )}

      {!algorithmType && (
        <div className='bg-muted/40 rounded-lg border p-2.5 text-xs'>
          <p className='text-foreground font-medium'>未选择关联算法</p>
          <p className='text-muted-foreground'>
            请先在「基础」页签选择关联算法：策略下拉与保存按钮将保持禁用。
          </p>
        </div>
      )}

      {!canEdit && (
        <p className='text-destructive text-xs'>当前账号缺少 algorithm:param_manage 权限，本页签只读。</p>
      )}

      {config.state === 'error' && (
        <div className='flex flex-wrap items-center gap-2'>
          <p className='text-destructive text-xs'>
            参数配置读取失败，未就绪时不能保存（整份保存会清空既有覆盖行）。
          </p>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 text-xs'
            onClick={() => config.refetch()}
          >
            重试
          </Button>
        </div>
      )}

      {/* 策略绑定 */}
      <div className='space-y-1.5'>
        <Label>参数策略</Label>
        <div className='flex flex-wrap items-center gap-2'>
          <Select
            value={boundProfileId == null ? UNBOUND : String(boundProfileId)}
            items={profilesForSelect}
            onValueChange={(value) => {
              if (!value) return
              bindMutation.mutate(value === UNBOUND ? null : Number(value))
            }}
            disabled={!canPersist || bindMutation.isPending}
          >
            <SelectTrigger className='w-56 justify-between' aria-label='参数策略'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {profilesForSelect.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 text-xs'
            disabled={!canPersist || !configReady || createMutation.isPending}
            onClick={() => openNameDialog('create')}
          >
            另存为新策略
          </Button>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 text-xs'
            disabled={!canPersist || boundProfileId == null || cloneMutation.isPending}
            onClick={() => openNameDialog('clone')}
          >
            克隆当前策略
          </Button>
        </div>
        <p className='text-muted-foreground text-xs'>
          策略提供默认字段与映射；本页的增删改写入 API 实例覆盖行（覆盖优先于策略）。
          切换下拉即保存绑定，选「未绑定」表示只使用本实例的覆盖行。
        </p>
      </div>

      {/* 输入映射（用例参数 → API 输入字段） */}
      <div className='space-y-1.5'>
        <div className='flex items-center justify-between'>
          <Label>输入映射</Label>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1 text-xs'
            disabled={!editable}
            onClick={() =>
              setInputMappingRows((rows) => [
                ...rows,
                {
                  key: rowKeyRef.current++,
                  source: 'case',
                  sourceDirection: 'input',
                  sourceParam: '',
                  targetParam: '',
                  transformType: 'none',
                },
              ])
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            新增输入映射
          </Button>
        </div>
        <p className='text-muted-foreground text-xs'>
          用例参数（左）供给 API 输入字段（右）；不配则按同名字段直接取。
        </p>
        <datalist id='case-param-codes'>
          {config.caseParams.map((param) => (
            <option key={param.paramCode} value={param.paramCode}>
              {param.paramName ?? ''}
            </option>
          ))}
        </datalist>
        {config.state === 'loading' ? (
          <div className='text-muted-foreground flex items-center justify-center gap-2 py-4 text-xs'>
            <Spinner className='size-4' />
            正在读取参数配置…
          </div>
        ) : inputMappingRows.length === 0 ? (
          <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
            未配置输入映射：用例参数与 API 输入字段同名时可直接取到值。
          </p>
        ) : (
          <div className='space-y-1.5'>
            {inputMappingRows.map((row) => (
              <div key={row.key} className='flex flex-wrap items-center gap-2'>
                <Input
                  list='case-param-codes'
                  aria-label='用例参数代码'
                  placeholder='用例参数代码'
                  className='h-7 w-40 font-mono text-xs'
                  value={row.sourceParam}
                  disabled={!editable}
                  onChange={(e) =>
                    setInputMappingRows((rows) =>
                      rows.map((item) =>
                        item.key === row.key ? { ...item, sourceParam: e.target.value } : item
                      )
                    )
                  }
                />
                <span className='text-muted-foreground text-xs'>→</span>
                <Select
                  value={row.targetParam || UNSET}
                  items={[{ value: UNSET, label: '选择 API 输入字段' }, ...inputTargetOptions]}
                  onValueChange={(value) =>
                    setInputMappingRows((rows) =>
                      rows.map((item) =>
                        item.key === row.key
                          ? { ...item, targetParam: !value || value === UNSET ? '' : value }
                          : item
                      )
                    )
                  }
                  disabled={!editable}
                >
                  <SelectTrigger size='sm' className='w-48' aria-label='API 输入字段'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={UNSET}>选择 API 输入字段</SelectItem>
                    {inputTargetOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={row.transformType}
                  items={TRANSFORM_TYPE_OPTIONS}
                  onValueChange={(value) =>
                    setInputMappingRows((rows) =>
                      rows.map((item) =>
                        item.key === row.key
                          ? { ...item, transformType: value as ParamTransformType }
                          : item
                      )
                    )
                  }
                  disabled={!editable}
                >
                  <SelectTrigger size='sm' className='w-28' aria-label='转换类型'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TRANSFORM_TYPE_OPTIONS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type='button'
                  variant='ghost'
                  size='icon-xs'
                  aria-label='删除输入映射'
                  disabled={!editable}
                  onClick={() =>
                    setInputMappingRows((rows) => rows.filter((item) => item.key !== row.key))
                  }
                >
                  <Trash2 aria-hidden='true' className='size-3.5' />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 输出字段（可编辑） */}
      <div className='space-y-1.5'>
        <div className='flex items-center justify-between'>
          <Label>输出字段</Label>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1 text-xs'
            disabled={!editable}
            onClick={() =>
              setOutputRows((rows) => [
                ...rows,
                {
                  key: rowKeyRef.current++,
                  paramCode: '',
                  paramName: '',
                  paramType: 'text',
                  required: false,
                  defaultValue: '',
                  helpText: '',
                  hidden: false,
                  label: null,
                  validationRules: null,
                  uiOrder: String(rows.length + 1),
                  fieldPath: '',
                },
              ])
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            新增输出字段
          </Button>
        </div>
        {config.state === 'loading' ? (
          <div className='text-muted-foreground flex items-center justify-center gap-2 py-6 text-xs'>
            <Spinner className='size-4' />
            正在读取参数配置…
          </div>
        ) : outputRows.length === 0 ? (
          <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
            当前策略与本实例均无输出字段声明；可新增行后保存。
          </p>
        ) : (
          <div className='border-border/60 min-w-0 overflow-x-auto rounded-lg border'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='text-xs'>参数代码</TableHead>
                  <TableHead className='text-xs'>参数名称</TableHead>
                  <TableHead className='text-xs'>类型</TableHead>
                  <TableHead className='text-xs'>方向</TableHead>
                  <TableHead className='text-xs'>排序</TableHead>
                  <TableHead className='text-xs'>响应路径</TableHead>
                  <TableHead className='text-xs'>默认值</TableHead>
                  <TableHead className='text-xs'>帮助提示</TableHead>
                  <TableHead className='text-xs'>必填</TableHead>
                  <TableHead className='text-xs'>隐藏</TableHead>
                  <TableHead className='w-10 text-xs'>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {outputRows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell>
                      <Input
                        value={row.paramCode}
                        disabled={!editable}
                        aria-label='参数代码'
                        className='h-7 w-28 font-mono text-xs'
                        onChange={(e) => updateOutputRow(row.key, { paramCode: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.paramName}
                        disabled={!editable}
                        aria-label='参数名称'
                        className='h-7 w-28 text-xs'
                        onChange={(e) => updateOutputRow(row.key, { paramName: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.paramType}
                        items={paramTypeOptionsOf(row.paramType)}
                        onValueChange={(value) =>
                          updateOutputRow(row.key, { paramType: value ?? 'text' })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-28' aria-label='参数类型'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {paramTypeOptionsOf(row.paramType).map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Badge variant='secondary'>输出</Badge>
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.uiOrder}
                        disabled={!editable}
                        type='number'
                        aria-label='排序'
                        className='h-7 w-16 text-xs'
                        onChange={(e) => updateOutputRow(row.key, { uiOrder: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.fieldPath}
                        disabled={!editable}
                        aria-label='响应路径'
                        placeholder='data.items[0].text'
                        className='h-7 w-40 font-mono text-xs'
                        onChange={(e) => updateOutputRow(row.key, { fieldPath: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.defaultValue}
                        disabled={!editable}
                        aria-label='默认值'
                        placeholder='default_value'
                        className='h-7 w-32 font-mono text-xs'
                        onChange={(e) =>
                          updateOutputRow(row.key, { defaultValue: e.target.value })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.helpText}
                        disabled={!editable}
                        aria-label='帮助提示'
                        placeholder='填写说明'
                        className='h-7 w-40 text-xs'
                        onChange={(e) => updateOutputRow(row.key, { helpText: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Checkbox
                        aria-label={`必填 ${row.paramCode || '新字段'}`}
                        checked={row.required}
                        disabled={!editable}
                        onCheckedChange={(checked) =>
                          updateOutputRow(row.key, { required: Boolean(checked) })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Checkbox
                        aria-label={`隐藏 ${row.paramCode || '新字段'}`}
                        checked={row.hidden}
                        disabled={!editable}
                        onCheckedChange={(checked) =>
                          updateOutputRow(row.key, { hidden: Boolean(checked) })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon-sm'
                        className='size-6 text-destructive'
                        aria-label='删除输出字段'
                        disabled={!editable}
                        onClick={() =>
                          setOutputRows((rows) => rows.filter((item) => item.key !== row.key))
                        }
                      >
                        <Trash2 aria-hidden='true' className='size-3.5' />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* 映射（可编辑） */}
      <div className='space-y-1.5'>
        <div className='flex items-center justify-between'>
          <Label>参数映射</Label>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1 text-xs'
            disabled={!editable}
            onClick={() =>
              setMappingRows((rows) => [
                ...rows,
                {
                  key: rowKeyRef.current++,
                  source: 'api',
                  sourceDirection: 'output',
                  sourceParam: '',
                  targetParam: '',
                  dimensionId: '',
                  transformType: 'none',
                },
              ])
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            新增映射
          </Button>
        </div>
        {config.state === 'loading' ? null : mappingRows.length === 0 ? (
          <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
            当前策略与本实例均无 API 输出映射；可新增行后保存。
          </p>
        ) : (
          <div className='border-border/60 min-w-0 overflow-x-auto rounded-lg border'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='text-xs'>来源</TableHead>
                  <TableHead className='text-xs'>来源方向</TableHead>
                  <TableHead className='text-xs'>源参数</TableHead>
                  <TableHead className='text-xs'>目标维度</TableHead>
                  <TableHead className='text-xs'>目标参数</TableHead>
                  <TableHead className='text-xs'>转换</TableHead>
                  <TableHead className='w-10 text-xs'>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mappingRows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell>
                      <Select
                        value={row.source}
                        items={MAPPING_SOURCE_OPTIONS}
                        onValueChange={(value) =>
                          updateMappingRow(row.key, {
                            source: value as ParamProfileMappingSource,
                          })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-28' aria-label='映射来源'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {MAPPING_SOURCE_OPTIONS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.sourceDirection}
                        items={MAPPING_DIRECTION_OPTIONS}
                        onValueChange={(value) =>
                          updateMappingRow(row.key, {
                            sourceDirection: value as ParamDirection,
                          })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-20' aria-label='来源方向'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {MAPPING_DIRECTION_OPTIONS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.sourceParam || UNSET}
                        items={[
                          { value: UNSET, label: '未选择' },
                          ...outputParamOptions,
                        ]}
                        onValueChange={(value) =>
                          updateMappingRow(row.key, {
                            sourceParam: !value || value === UNSET ? '' : value,
                          })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-40' aria-label='源参数'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={UNSET}>未选择</SelectItem>
                          {outputParamOptions.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.dimensionId || UNSET}
                        items={[
                          { value: UNSET, label: '不指定维度' },
                          ...config.dimensions.map((dimension) => ({
                            value: String(dimension.id),
                            label: dimension.name,
                          })),
                        ]}
                        onValueChange={(value) =>
                          // 维度变了，目标参数重置（不同维度的参数不同）
                          updateMappingRow(row.key, {
                            dimensionId: !value || value === UNSET ? '' : value,
                            targetParam: '',
                          })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-36' aria-label='目标维度'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={UNSET}>不指定维度</SelectItem>
                          {config.dimensions.map((dimension) => (
                            <SelectItem key={dimension.id} value={String(dimension.id)}>
                              {dimension.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <TargetParamSelect
                        dimensionId={
                          row.dimensionId.trim() === '' ? null : Number(row.dimensionId)
                        }
                        value={row.targetParam}
                        disabled={!editable}
                        onChange={(value) =>
                          updateMappingRow(row.key, { targetParam: value })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.transformType}
                        items={TRANSFORM_TYPE_OPTIONS}
                        onValueChange={(value) =>
                          updateMappingRow(row.key, {
                            transformType: value as ParamTransformType,
                          })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-32' aria-label='转换类型'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TRANSFORM_TYPE_OPTIONS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon-sm'
                        className='size-6 text-destructive'
                        aria-label='删除映射'
                        disabled={!editable}
                        onClick={() =>
                          setMappingRows((rows) => rows.filter((item) => item.key !== row.key))
                        }
                      >
                        <Trash2 aria-hidden='true' className='size-3.5' />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className='flex items-center justify-end gap-2'>
        {persisted ? (
          <Button
            type='button'
            size='sm'
            disabled={!canPersist || !configReady || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? '保存中…' : '保存参数配置'}
          </Button>
        ) : (
          <p className='text-muted-foreground text-xs'>
            新建态：本页草稿随底部「保存」一起提交，无需单独保存。
          </p>
        )}
      </div>

      {/* 另存 / 克隆：名称 + 描述 */}
      <Dialog open={nameDialog != null} onOpenChange={(open) => !open && setNameDialog(null)}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>{nameDialog === 'clone' ? '克隆当前策略' : '另存为新策略'}</DialogTitle>
            <DialogDescription>
              {nameDialog === 'clone'
                ? '复制当前绑定策略的字段与映射，生成新策略并绑定到本 API。'
                : '以本页当前字段与映射创建新策略，并绑定到本 API。'}
            </DialogDescription>
          </DialogHeader>
          <div className='space-y-3'>
            <div className='space-y-1.5'>
              <Label htmlFor='param-profile-name'>策略名称 *</Label>
              <Input
                id='param-profile-name'
                value={draftName}
                maxLength={100}
                placeholder='请输入策略名称'
                onChange={(e) => setDraftName(e.target.value)}
              />
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='param-profile-description'>描述</Label>
              <Textarea
                id='param-profile-description'
                rows={2}
                value={draftDescription}
                placeholder='可选：说明字段来源 / 适用场景'
                onChange={(e) => setDraftDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setNameDialog(null)}>
              取消
            </Button>
            <Button type='button' disabled={nameDialogPending} onClick={submitNameDialog}>
              {nameDialogPending ? '保存中…' : '确定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
