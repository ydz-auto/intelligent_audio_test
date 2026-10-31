/**
 * 新增/编辑 API 弹窗（INT-1777 骨架 + T4.2 参数配置页签）。
 * INT-2153：设备管理「测试 API」页签的「添加测试API」也开本弹窗（新增态 = 不传 api），
 * 与行内「编辑」同一套表单——设备抽屉不再承载 API，创建时即可配 meta。
 *
 * 四个页签：
 * - 基础：现有字段（名称 / 关联算法 / 最大并发 / 协议 + 流式性 / 描述 / 端点列表与密钥池），
 *   新增 audio_config 编辑区（顶层列 apis.audio_config，输入 / 输出两套格式可不同）；
 * - 请求模板：写 meta（协议决定请求/响应配置区，流式性决定轮次/会话配置区）；
 * - 响应解析：写 meta（result_parser 等 8 个解析器键；顶部固定提示 C0 裁定口径）；
 * - 参数配置：API 实例作用域（策略绑定 + 输出字段 / 映射可编辑 + 覆盖保存），
 *   见 features/test-execution/modals/api-param-config-tab。
 *
 * 协议 × 流式性（INT-1800 / B0）：两维独立可组合，下拉 4 值、未上线协议置灰并提示；
 * 流式开关按 B0 §3.2.3 可用矩阵锁定（仅 sse 只支持流式；http / websocket / grpc 两种都可写）。
 * 保存只提交 protocol / streaming，永不提交 `device_type`（后端写侧显式 400）。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { Plus, Upload, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { useApiParamConfig } from '@/application/test-execution/useApiParamConfig'
import { useApisCrud } from '@/application/test-execution/useApisCrud'
import { useTestAlgorithmOptions } from '@/application/test-execution/useTestAlgorithmOptions'
import { usePermissions } from '@/application/hooks/use-permissions'
import { ApiParamConfigTab } from '@/features/test-execution/modals/api-param-config-tab'
import { fetchApi, parseApiResponsePreview, uploadApiProto } from '@/infrastructure/api/test-execution-api'
import { createProfile, getProfile, listProfiles } from '@/infrastructure/api/param-profile-api'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import type {
  ApiConfig,
  ApiParsePreviewResult,
  ApiProtoField,
  ApiProtoSymbolTable,
} from '@/domain/models/apiConfig'
import {
  API_PROTOCOLS,
  API_PROTOCOL_LABEL,
  DEFAULT_API_PROTOCOL,
  DEFAULT_API_STREAMING,
  apiProtocolOptions,
  defaultStreamingFor,
  isApiProtocol,
  isStreamingLocked,
  streamingLabel,
  unavailableCombinationReason,
  type ApiProtocol,
} from '@/domain/models/apiProtocol'
import { cn } from '@/lib/utils'
import { evaluateAdapterCapability } from '@/domain/models/adapterSpec'
import type { ApiConfigSnapshot, ApiScopeOverridesInput } from '@/domain/models/paramProfile'
import { inferBodyTemplate, inferResponseParser } from '@/domain/models/sampleInference'
import { VENDOR_ADAPTER_OPTIONS } from '@/domain/models/vendorAdapter'

import {
  AUDIO_DIRECTION_FIELDS,
  AUDIO_BIT_DEPTH_OPTIONS,
  AUDIO_CHANNEL_OPTIONS,
  AUDIO_CONTAINER_OPTIONS,
  AUDIO_SAMPLE_RATE_OPTIONS,
  AUDIO_FRAME_HINT,
  ENDPOINT_NUMERIC_RULES,
  FIRST_FRAME_HINT,
  GRPC_METADATA_SECRET_KEYS,
  GRPC_METHOD_KINDS,
  HTTP_METHOD_OPTIONS,
  SSE_DEFAULTS,
  SSE_FIELD_LIMITS,
  audioConfigDraftFrom,
  buildAudioConfig,
  emptyAudioConfigDraft,
  emptyRequestTemplateDraft,
  emptyResponseParserDraft,
  deriveFieldsFromMeta,
  mergeRequestTemplateMeta,
  mergeResponseParserMeta,
  newKeyValueRow,
  requestTemplateDraftFromMeta,
  responseParserDraftFromMeta,
  validateEndpointNumbers,
  type AppendModeValue,
  type AudioConfigDraft,
  type AudioDirection,
  type AudioFormatDraft,
  type BodyTemplateMode,
  type EndpointNumericErrors,
  type EndpointNumericField,
  type KeyValueRow,
  type MetaDraftError,
  type RequestTemplateDraft,
  type ResponseParserDraft,
  type ResponseParserDraftError,
} from './api-edit-dialog-model'

const MAX_PROCESS_MESSAGE = '请输入 1~128 的整数'

const apiFormSchema = z.object({
  name: z.string().min(1, '请输入必填项'),
  algorithmType: z.string().min(1, '请输入必填项'),
  // INT-1939：留空（valueAsNumber → NaN）/ 越界都要落到中文内联提示，不靠浏览器原生气泡
  maxProcess: z
    .number({ message: MAX_PROCESS_MESSAGE })
    .int(MAX_PROCESS_MESSAGE)
    .min(1, MAX_PROCESS_MESSAGE)
    .max(128, MAX_PROCESS_MESSAGE),
  description: z.string().optional(),
  // INT-1800：协议 + 流式开关两个独立维度（不再有 device_type 三选）
  protocol: z.enum(API_PROTOCOLS, { message: '请选择协议' }),
  streaming: z.boolean(),
})

type ApiForm = z.infer<typeof apiFormSchema>

type ApiTab = 'basic' | 'request' | 'response' | 'param'

const API_TABS: ReadonlyArray<{ value: ApiTab; label: string }> = [
  { value: 'basic', label: '基础' },
  { value: 'request', label: '请求模板' },
  { value: 'response', label: '响应解析' },
  { value: 'param', label: '参数配置' },
]

/** base-ui Select 不接受空串为「未设置」，统一用哨兵值映射草稿里的 '' */
const UNSET = '__unset__'

// base-ui Select 关闭态用 items 显示 label（否则直接回显 value；INT-1633 同口径）
const UNSET_OPTION = { value: UNSET, label: '未设置' }
/** 协议下拉（INT-1800）：4 值全列，sse / grpc 置灰并提示「协议实现未上线」 */
const PROTOCOL_OPTIONS = apiProtocolOptions()
const METHOD_OPTIONS = [
  UNSET_OPTION,
  ...HTTP_METHOD_OPTIONS.map((method) => ({ value: method, label: method })),
]
/** gRPC method_kind（`grpc_client.find_method` 只认这三值；与 descriptor 不一致执行期报错） */
const GRPC_METHOD_KIND_OPTIONS = [
  UNSET_OPTION,
  ...GRPC_METHOD_KINDS.map((kind) => ({
    value: kind,
    label:
      kind === 'unary'
        ? 'unary（一元）'
        : kind === 'server_stream'
          ? 'server_stream（服务端流）'
          : 'bidi（双向流）',
  })),
]
const SAMPLE_RATE_OPTIONS = [
  UNSET_OPTION,
  ...AUDIO_SAMPLE_RATE_OPTIONS.map((rate) => ({ value: String(rate), label: `${rate} Hz` })),
]
const BIT_DEPTH_OPTIONS = [
  UNSET_OPTION,
  ...AUDIO_BIT_DEPTH_OPTIONS.map((depth) => ({ value: depth, label: depth })),
]
const CHANNEL_OPTIONS = [
  UNSET_OPTION,
  ...AUDIO_CHANNEL_OPTIONS.map((channel) => ({
    value: String(channel),
    label: channel === 1 ? '1（单声道）' : '2（立体声）',
  })),
]
const CONTAINER_OPTIONS = [
  UNSET_OPTION,
  ...AUDIO_CONTAINER_OPTIONS.map((container) => ({ value: container, label: container })),
]
const BODY_TEMPLATE_MODE_OPTIONS = [
  { value: 'json', label: '结构化 JSON' },
  { value: 'raw', label: '原始字符串模板' },
] as const
// INT-1778 append_mode 三态（'' = 不写该键，沿用后端缺省）
const APPEND_MODE_OPTIONS = [
  { value: UNSET, label: '未设置（按缺省：流式取最后一条）' },
  { value: 'true', label: '是（逐句结束追加拼接）' },
  { value: 'false', label: '否（保留最后一条分片）' },
] as const

/** 端点编辑行（INT-1223：复用 device-mutate-drawer 端点编辑器形态；端点四整数校验项齐全——INT-1362 补优先级/音频时长） */
interface EndpointFormRow {
  key: string
  endpoint: string
  name: string
  priority: string
  maxProcess: string
  maxTimeout: string
  maxAudioDuration: string
  /** INT-1437 密钥池：textarea 草稿（瞬态，保存时 adapter 拆行转 api_keys） */
  apiKeysText: string
  /** 密钥池摘要（编辑回显「已配置 N 个密钥 / 尾号…」，完整密钥不回显） */
  apiKeysSummary: { count: number; tails: string[] } | null
}

const ENDPOINT_EMPTY: EndpointFormRow = {
  key: '',
  endpoint: '',
  name: '',
  priority: '1',
  maxProcess: '1',
  maxTimeout: '30',
  maxAudioDuration: '60',
  apiKeysText: '',
  apiKeysSummary: null,
}

function endpointKey(): string {
  return Math.random().toString(36).slice(2, 9)
}

/**
 * 表单初值 = 每次打开的重置值（INT-1777 复测 P2-1）。
 * `useForm({ values })` 只在深比较变化时重置，而编辑对象跨开合是同一个引用：
 * 取消（或关闭）后重开必须复位，否则上次取消的输入会残留、并在重开直接保存时被写库。
 */
function computeFormValues(
  api: ApiConfig | undefined,
  algorithmList: ReadonlyArray<{ id: string; name: string }>,
  globalAlgorithmId: string
): ApiForm {
  return {
    name: api?.name ?? '',
    // 关联算法的存储值是**算法类型码**（apis.algorithm_type，缺省取全局算法；INT-1778 修：
    // 原实现回填/提交的是显示名，导致 api 的 algorithm_type 落成「小艺语音大模型」，
    // 按类型码取参数的输出字段 / 映射页签恒空）
    algorithmType:
      api?.algorithmType ??
      algorithmList.find((a) => a.id === globalAlgorithmId)?.id ??
      '',
    maxProcess: api?.defaultMaxProcess ?? 5,
    description: api?.description ?? '',
    // INT-1800：协议 / 流式性按读侧两列回填；缺失（旧后端未升级）时按新建缺省 http / 非流式，
    // 并保持两维自洽（协议缺省必与其可用组合一致）
    protocol: isApiProtocol(api?.protocol) ? api.protocol : DEFAULT_API_PROTOCOL,
    streaming: api?.streaming ?? DEFAULT_API_STREAMING,
  }
}

interface ApiEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 传入 = 编辑；undefined = 新增 */
  api?: ApiConfig
}

export function ApiEditDialog({ open, onOpenChange, api }: ApiEditDialogProps) {
  const { save } = useApisCrud()
  const globalAlgorithmId = useAlgorithmStore((s) => s.algorithmId)
  const { data: algorithmOptions } = useTestAlgorithmOptions()
  const algorithmList = algorithmOptions ?? []
  const [tab, setTab] = useState<ApiTab>('basic')
  const [endpoints, setEndpoints] = useState<EndpointFormRow[]>([])
  // INT-1939 返工：端点行四项整数的字段级错误（按行 key 分组；表单 noValidate 后由 zod / 自查替代原生约束）
  const [endpointErrors, setEndpointErrors] = useState<Record<string, EndpointNumericErrors>>({})
  // 请求模板页签草稿（meta 键级合并；未触碰不发 meta）
  const [metaDraft, setMetaDraft] = useState<RequestTemplateDraft>(emptyRequestTemplateDraft)
  const [metaTouched, setMetaTouched] = useState(false)
  const [metaErrors, setMetaErrors] = useState<MetaDraftError[]>([])
  // INT-1778 响应解析页签草稿（同样写 meta，与请求模板各自 dirty、保存时串行合并）
  const [responseDraft, setResponseDraft] = useState<ResponseParserDraft>(emptyResponseParserDraft)
  const [responseTouched, setResponseTouched] = useState(false)
  const [responseErrors, setResponseErrors] = useState<ResponseParserDraftError[]>([])
  // 「参数配置」页签有独立保存钮，底部「保存」不落这些改动：上报未保存状态用于拦截
  const [paramConfigDirty, setParamConfigDirty] = useState(false)
  // 新建态参数配置草稿：API 创建成功后随保存一起提交（api-scope 覆盖行）
  const [paramConfigDraft, setParamConfigDraft] =
    useState<Omit<ApiScopeOverridesInput, 'algorithmType'> | null>(null)
  // audio_config 草稿（顶层列；未改动不发该键）
  const [audioDraft, setAudioDraft] = useState<AudioConfigDraft>(emptyAudioConfigDraft)
  const [audioTouched, setAudioTouched] = useState(false)
  const [audioCleared, setAudioCleared] = useState(false)
  // 配置策略（API 配置快照 + 参数配置）：套用 / 另存
  const [applyProfileId, setApplyProfileId] = useState('')
  const [strategyDialogOpen, setStrategyDialogOpen] = useState(false)
  const [strategyName, setStrategyName] = useState('')
  const [strategySaving, setStrategySaving] = useState(false)
  // A3（INT-1791）：gRPC 符号表（仅上传端点返回时才有；端点未部署 → 恒为 null，service/method 走手填）
  const [protoSymbols, setProtoSymbols] = useState<ApiProtoSymbolTable | null>(null)
  const [protoUploading, setProtoUploading] = useState(false)
  const [protoUploadError, setProtoUploadError] = useState<string | null>(null)
  const protoFileRef = useRef<HTMLInputElement>(null)

  // INT-1777：打开弹窗时取一次该 API 的最新读侧快照作 meta / audio_config 合并 base。
  // 列表快照可能早于别的改动（meta 后端整块 replace），拿陈旧 base 合并会静默丢未知键。
  const detailQuery = useQuery({
    queryKey: ['test-execution', 'api-detail', api?.id ?? null],
    queryFn: () => fetchApi(api!.id),
    enabled: open && api?.id != null,
    staleTime: 0,
  })
  const baseApi = detailQuery.data ?? api

  const form = useForm<ApiForm>({
    resolver: zodResolver(apiFormSchema),
    values: computeFormValues(api, algorithmList, globalAlgorithmId),
  })

  const watchedProtocol = form.watch('protocol')
  const watchedStreaming = form.watch('streaming')
  const algorithmType = form.watch('algorithmType')

  const { hasPermission } = usePermissions()

  // T4.2 参数配置数据源：API 实例作用域（策略 + 本 API 覆盖行）。
  // 只在打开且停留在「响应解析 / 参数配置」页签时取数，新建 API（无 id）不发请求。
  // 响应解析页签的 C0 判定同样依赖这份解析结果（有无 direction=output 行）。
  const apiParamConfig = useApiParamConfig(
    api?.id ?? null,
    algorithmType,
    open && (tab === 'response' || tab === 'param')
  )
  const canManageParams = hasPermission('algorithm:param_manage')

  // 端点列表（唯一端点入口；编辑回显，关闭清空）
  useEffect(() => {
    if (open && api) {
      setEndpoints(
        (api.endpoints ?? []).map((ep) => ({
          key: endpointKey(),
          endpoint: ep.endpoint,
          name: ep.name ?? '',
          priority: String(ep.priority ?? 1),
          maxProcess: String(ep.maxProcess ?? 1),
          maxTimeout: String(ep.maxTimeout ?? 30),
          maxAudioDuration: String(ep.maxAudioDuration ?? 60),
          apiKeysText: '',
          apiKeysSummary: ep.apiKeysSummary ?? null,
        }))
      )
    } else if (!open) {
      setEndpoints([])
    }
  }, [open, api])

  // 每次打开重置页签、草稿与表单（关闭再打开不残留上次输入，含取消后的表单字段）
  useEffect(() => {
    if (!open) return
    // P2-1：values 深比较在同引用 api 上不会触发重置，开合必须显式 reset
    form.reset(computeFormValues(api, algorithmList, globalAlgorithmId))
    setTab('basic')
    setEndpointErrors({})
    setMetaDraft(requestTemplateDraftFromMeta(api?.meta))
    setMetaTouched(false)
    setMetaErrors([])
    setResponseDraft(responseParserDraftFromMeta(api?.meta))
    setResponseTouched(false)
    setResponseErrors([])
    setAudioDraft(audioConfigDraftFrom(api?.audioConfig))
    setAudioTouched(false)
    setAudioCleared(false)
    // A3：符号表只在本次上传端点返回后存在；开合不复用上次结果（否则会拿旧 service 列表配新 API）
    setProtoSymbols(null)
    setProtoUploading(false)
    setProtoUploadError(null)
    // algorithmList / globalAlgorithmId 只作打开瞬间的缺省算法来源，迟到的选项由 values 深比较补齐
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, api])

  // 最新快照到达后刷新草稿（用户已触碰的字段不覆盖）
  useEffect(() => {
    if (!open || !detailQuery.data) return
    const fresh = detailQuery.data
    if (!metaTouched) setMetaDraft(requestTemplateDraftFromMeta(fresh.meta))
    if (!responseTouched) setResponseDraft(responseParserDraftFromMeta(fresh.meta))
    if (!audioTouched) {
      setAudioDraft(audioConfigDraftFrom(fresh.audioConfig))
      setAudioCleared(false)
    }
  }, [open, detailQuery.data, metaTouched, responseTouched, audioTouched])

  // 页签显隐依据（INT-1800 / B0 §3.5）：协议决定请求配置区，流式性决定轮次/会话配置区
  const requestTarget = { protocol: watchedProtocol, streaming: watchedStreaming }
  const isWebSocket = watchedProtocol === 'websocket'
  const streamingLocked = isStreamingLocked(watchedProtocol)
  // 组合不在可用矩阵内（存量脏数据 / 旧后端）→ 明示后端会 400，不静默改写用户的选择
  const combinationWarning = unavailableCombinationReason(watchedProtocol, watchedStreaming)

  // 关窗即清「参数配置未保存」标记（下次打开从服务端重新回读）
  useEffect(() => {
    if (!open) setParamConfigDirty(false)
  }, [open])

  // 厂商适配器候选：受控词表（后端 VendorAdapterType 同值域）+ 存量未知值兜底展示，
  // 不静默改写用户已存的值，也不允许自由输入写错。
  const vendorAdapterOptions = useMemo(() => {
    const current = metaDraft.vendorAdapter.trim()
    const options = VENDOR_ADAPTER_OPTIONS.map((item) => ({
      value: item.value === '' ? UNSET : item.value,
      label: item.label,
      hint: item.hint,
    }))
    if (current && !VENDOR_ADAPTER_OPTIONS.some((item) => item.value === current)) {
      options.push({
        value: current,
        label: `当前值：${current}（未注册）`,
        hint: '该值执行期会被拒绝，请改选标准值或留空',
      })
    }
    return options
  }, [metaDraft.vendorAdapter])

  // 保存后的 meta 预览（请求模板 → 响应解析串行合并），供配置自检与字段推导共用
  const previewMeta = useMemo(() => {
    const base = baseApi?.meta ?? {}
    try {
      let preview: Record<string, unknown> = mergeRequestTemplateMeta(base, metaDraft, {
        protocol: watchedProtocol,
        streaming: watchedStreaming,
      }).meta
      if (responseTouched) {
        preview = mergeResponseParserMeta(preview, responseDraft).meta
      }
      return preview
    } catch {
      return base
    }
  }, [
    baseApi?.meta,
    metaDraft,
    responseDraft,
    responseTouched,
    watchedProtocol,
    watchedStreaming,
  ])

  // 「纯配置能否跑」自检：说清是「配置即可」还是「缺必填/需适配器」。
  const capability = useMemo(
    () =>
      evaluateAdapterCapability({
        protocol: watchedProtocol,
        streaming: watchedStreaming,
        meta: previewMeta,
      }),
    [watchedProtocol, watchedStreaming, previewMeta]
  )

  // 参数配置页签的自动字段：输入来自请求模板占位符，输出来自响应解析路径
  const derivedFields = useMemo(() => deriveFieldsFromMeta(previewMeta), [previewMeta])

  // C0（INT-1745）判定结果展示：按该 API 实例（策略 + 覆盖）的解析结果说明，不描述系统当前行为
  const c0Status = !algorithmType
    ? '未选择关联算法，无法判定'
    : api?.id == null
      ? '新建 API 保存后可用，无法判定'
      : apiParamConfig.state === 'loading'
        ? '正在读取该 API 的输出字段声明…'
        : apiParamConfig.state === 'ready'
          ? apiParamConfig.noOutputDeclared
            ? '该 API 未声明输出字段 → 解析走本页 meta 兜底'
            : `该 API 已声明 ${apiParamConfig.outputParams.length} 个输出字段 → 本页解析器不兜底`
          : apiParamConfig.state === 'forbidden'
            ? '无权查看参数配置，无法判定'
            : apiParamConfig.state === 'error'
              ? '参数配置读取失败，无法判定'
              : '未判定'

  const metaErrorOf = (field: MetaDraftError['field']) =>
    metaErrors.find((error) => error.field === field)?.message

  const updateMeta = (patch: Partial<RequestTemplateDraft>) => {
    setMetaDraft((prev) => ({ ...prev, ...patch }))
    setMetaTouched(true)
    setMetaErrors([])
  }

  // ---- A3 gRPC 符号表联动（上传端点未部署时 protoSymbols 恒为 null → service/method 手填） ----
  const grpcServiceSymbol =
    protoSymbols?.services.find((service) => service.name === metaDraft.grpcService) ?? null
  const grpcMethodSymbol =
    grpcServiceSymbol?.methods.find((method) => method.name === metaDraft.grpcMethod) ?? null
  const grpcServiceOptions = (protoSymbols?.services ?? []).map((service) => ({
    value: service.name,
    label: service.name,
  }))
  const grpcMethodOptions = (grpcServiceSymbol?.methods ?? []).map((method) => ({
    value: method.name,
    label: `${method.name}（${method.methodKind}）`,
  }))
  /** deadline 缺省 = 端点超时 × 1000（`grpc_adapter.deadline_ms`）；只作 placeholder */
  const grpcDeadlinePlaceholder = `留空 = 端点超时 ${
    endpoints[0]?.maxTimeout || '30'
  }s × 1000 = ${(Number(endpoints[0]?.maxTimeout) || 30) * 1000}`
  /** SSE idle_timeout 缺省同源（A2：`default_max_timeout × 1000`） */
  const sseIdlePlaceholder = `留空 = 端点超时 × 1000（${
    (Number(endpoints[0]?.maxTimeout) || 30) * 1000
  }）`

  const handleProtoFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    // 清空 input 值：同一文件二次选择也要触发 change
    event.target.value = ''
    if (!file) return
    setProtoUploading(true)
    setProtoUploadError(null)
    try {
      const table = await uploadApiProto(file)
      setProtoSymbols(table)
      updateMeta({
        grpcProtoObjectKey: table.objectKey,
        grpcProtoSha256: table.sha256,
        grpcProtoSize: String(table.size),
      })
    } catch (error) {
      // 端点未部署（INT-1952 未部署）→ 404 / 网络错误：如实展示，绝不回填假 object_key
      setProtoUploadError(
        error instanceof Error && error.message
          ? error.message
          : '协议文件上传失败：接口尚未上线'
      )
    } finally {
      setProtoUploading(false)
    }
  }

  const responseErrorOf = (field: ResponseParserDraftError['field']) =>
    responseErrors.find((error) => error.field === field)?.message

  const updateResponse = (patch: Partial<ResponseParserDraft>) => {
    setResponseDraft((prev) => ({ ...prev, ...patch }))
    setResponseTouched(true)
    setResponseErrors([])
  }

  const updateAudio = (direction: AudioDirection, patch: Partial<AudioFormatDraft>) => {
    setAudioDraft((prev) => ({
      ...prev,
      [direction]: { ...prev[direction], ...patch },
    }))
    setAudioTouched(true)
    setAudioCleared(false)
  }

  const clearAudioConfig = () => {
    setAudioDraft(emptyAudioConfigDraft())
    setAudioTouched(true)
    setAudioCleared(true)
  }

  /* ---------------- 配置策略（整份配置存/取） ---------------- */

  const profilesQuery = useQuery({
    queryKey: ['test-execution', 'api-dialog', 'param-profiles', algorithmType],
    queryFn: () => listProfiles(algorithmType, 'api'),
    enabled: open && Boolean(algorithmType),
    staleTime: 0,
    retry: false,
  })

  const profileOptions = useMemo(
    () => (profilesQuery.data?.profiles ?? []).map((item) => ({ value: String(item.id), label: item.name })),
    [profilesQuery.data]
  )

  /** 当前弹窗的全量配置快照（端点地址 / 密钥属实例私有，不进快照） */
  const buildConfigSnapshot = (): ApiConfigSnapshot => {
    let mergedMeta: Record<string, unknown> | null = baseApi?.meta ?? null
    if (metaTouched || responseTouched) {
      mergedMeta = mergeResponseParserMeta(
        mergeRequestTemplateMeta(baseApi?.meta ?? {}, metaDraft, requestTarget).meta,
        responseDraft
      ).meta
    }
    let audioConfig: Record<string, unknown> | null = baseApi?.audioConfig ?? null
    if (audioTouched) {
      audioConfig = audioCleared ? null : buildAudioConfig(baseApi?.audioConfig, audioDraft)
    }
    return {
      protocol: watchedProtocol,
      streaming: watchedStreaming,
      vendorAdapter: metaDraft.vendorAdapter.trim() || null,
      audioConfig,
      meta: mergedMeta,
    }
  }

  /** 把策略快照写回当前表单（协议 / 流式 / 音频 / meta 请求模板与响应解析） */
  const applyConfigSnapshot = (config: ApiConfigSnapshot | null) => {
    if (!config) return
    if (config.protocol && isApiProtocol(config.protocol)) {
      form.setValue('protocol', config.protocol)
    }
    if (config.streaming != null) {
      form.setValue('streaming', config.streaming)
    }
    if (config.audioConfig) {
      setAudioDraft(audioConfigDraftFrom(config.audioConfig))
      setAudioTouched(true)
      setAudioCleared(false)
    }
    if (config.meta) {
      setMetaDraft(requestTemplateDraftFromMeta(config.meta))
      setResponseDraft(responseParserDraftFromMeta(config.meta))
      setMetaTouched(true)
      setResponseTouched(true)
    }
  }

  /** 套用策略：新建态连同参数声明 / 映射一起作为创建草稿；编辑态只覆盖配置项 */
  const applyStrategy = async () => {
    if (!applyProfileId) return
    try {
      const profile = await getProfile(Number(applyProfileId))
      applyConfigSnapshot(profile.config)
      if (api?.id == null) {
        setParamConfigDraft({
          params: profile.params.map((param) => ({
            paramCode: param.paramCode,
            paramName: param.paramName,
            paramType: param.paramType,
            direction: param.direction,
            required: param.required,
            defaultValue: param.defaultValue,
            helpText: param.helpText,
            uiOrder: param.uiOrder,
            hidden: param.hidden,
            fieldPath: param.fieldPath,
          })),
          mappings: profile.mappings.map((mapping) => ({
            source: 'api' as const,
            sourceDirection: mapping.sourceDirection,
            sourceParam: mapping.sourceParam,
            targetParam: mapping.targetParam,
            dimensionId: mapping.dimensionId,
            transformType: mapping.transformType,
          })),
        })
      }
      toast.success('已套用策略配置；点「保存」后生效')
    } catch (error) {
      toast.error(`套用策略失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  /** 存为策略：当前全量配置（含参数声明 / 映射草稿）整份落库 */
  const saveAsStrategy = async () => {
    const name = strategyName.trim()
    if (!name) {
      toast.error('请填写策略名称')
      return
    }
    if (!algorithmType) {
      toast.error('请先选择关联算法')
      return
    }
    setStrategySaving(true)
    try {
      await createProfile({
        scope: 'api',
        algorithmType,
        name,
        description: null,
        status: 'online',
        config: buildConfigSnapshot(),
        params: paramConfigDraft?.params ?? [],
        mappings: paramConfigDraft?.mappings ?? [],
      })
      toast.success('已存为配置策略')
      setStrategyDialogOpen(false)
      setStrategyName('')
      void profilesQuery.refetch()
    } catch (error) {
      toast.error(`存为策略失败：${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setStrategySaving(false)
    }
  }

  const endpointErrorOf = (key: string, field: EndpointNumericField) =>
    endpointErrors[key]?.[field]

  const updateEndpoint = (key: string, patch: Partial<EndpointFormRow>) => {
    setEndpoints((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)))
    // 改过的字段立刻清掉该行提示，其余字段的错误保留到下次保存
    setEndpointErrors((prev) => {
      const rowErrors = prev[key]
      if (!rowErrors) return prev
      const remaining = { ...rowErrors }
      for (const field of Object.keys(patch)) delete remaining[field as EndpointNumericField]
      const next = { ...prev }
      if (Object.keys(remaining).length > 0) next[key] = remaining
      else delete next[key]
      return next
    })
  }

  const setEndpointNumber = (key: string, field: EndpointNumericField, value: string) => {
    const patch: Partial<EndpointFormRow> = {}
    patch[field] = value
    updateEndpoint(key, patch)
  }

  const addEndpoint = () => {
    setEndpoints((prev) => [...prev, { ...ENDPOINT_EMPTY, key: endpointKey() }])
  }

  const removeEndpoint = (key: string) => {
    setEndpoints((prev) => prev.filter((row) => row.key !== key))
    setEndpointErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const handleSave = async (values: ApiForm) => {
    // 编辑态：「参数配置」页签自带保存钮，这里拦下，避免用户以为底部保存已落参数改动；
    // 新建态（还没有 id）参数草稿随本次保存一起提交，不需要拦截。
    if (paramConfigDirty && api?.id != null) {
      setTab('param')
      toast.warning('「参数配置」还有未保存的改动，请先在该页签点「保存参数配置」')
      return
    }
    // INT-1939 返工：表单 noValidate 后原生 min/max 不再拦截，端点行四项整数在此自查
    // （口径同原原生约束：整数 + 区间；空串按缺省值兜底，不报错）。
    // 只校验会提交的行——端点 URL 为空的行整行不下发。
    const submittedEndpoints = endpoints.filter((row) => row.endpoint.trim())
    const rowErrors: Record<string, EndpointNumericErrors> = {}
    for (const row of submittedEndpoints) {
      const errors = validateEndpointNumbers(row)
      if (Object.keys(errors).length > 0) rowErrors[row.key] = errors
    }
    if (Object.keys(rowErrors).length > 0) {
      // 拦截提交：弹窗不关、留在基础页签（端点行所在页签）并逐字段给出中文内联提示
      setEndpointErrors(rowErrors)
      setTab('basic')
      return
    }
    setEndpointErrors({})

    const payload: Partial<ApiConfig> & { name: string } = {
      id: api?.id,
      name: values.name,
      algorithmType: values.algorithmType,
      defaultMaxProcess: values.maxProcess,
      description: values.description || null,
      // INT-1800：协议 + 流式性两维独立提交；`device_type` 永不出现（后端写了会 400）
      protocol: values.protocol,
      streaming: values.streaming,
      endpoints: submittedEndpoints.map((row) => ({
        id: null,
        endpoint: row.endpoint.trim(),
        name: row.name.trim() || null,
        priority: Number(row.priority) || 1,
        maxProcess: Number(row.maxProcess) || 1,
        maxTimeout: Number(row.maxTimeout) || 30,
        maxAudioDuration: Number(row.maxAudioDuration) || 60,
        status: 'online',
        healthScore: null,
        description: null,
        apiKeysSummary: row.apiKeysSummary,
        // INT-1437 密钥池：textarea 草稿瞬态透传，adapter 拆行转 api_keys 落库
        apiKeysText: row.apiKeysText,
      })),
    }

    // meta 写入（母卡 §3.1）：两个页签都未触碰 → 不下发 meta 键；
    // 触碰 → 以 base 为底按「请求模板 → 响应解析」串行合并，提交合并后的整对象。
    // A3：gRPC / SSE 的请求模板区块是**协议必填面**（后端执行期缺 meta.grpc 直接报错），
    // 即使用户没动过任何控件也要走一次合并 + 校验，否则会存下一个执行必失败的配置。
    const protocolBlockRequired = watchedProtocol === 'grpc' || watchedProtocol === 'sse'
    if (metaTouched || responseTouched || protocolBlockRequired) {
      let meta: Record<string, unknown> = baseApi?.meta ?? {}
      const requestResult =
        metaTouched || protocolBlockRequired
          ? mergeRequestTemplateMeta(meta, metaDraft, requestTarget)
          : { meta, errors: [] as MetaDraftError[] }
      meta = requestResult.meta
      const responseResult = responseTouched
        ? mergeResponseParserMeta(meta, responseDraft)
        : { meta, errors: [] as ResponseParserDraftError[] }
      meta = responseResult.meta

      setMetaErrors(requestResult.errors)
      setResponseErrors(responseResult.errors)
      if (requestResult.errors.length > 0 || responseResult.errors.length > 0) {
        // 非法 JSON 保存前拦截：弹窗不关、请求不发出，并跳到第一个出错的页签
        setTab(requestResult.errors.length > 0 ? 'request' : 'response')
        return
      }
      payload.meta = meta
    }
    // audio_config（顶层列）：未改动 → 不下发；显式清除 → {}
    if (audioTouched) {
      payload.audioConfig = audioCleared ? {} : buildAudioConfig(baseApi?.audioConfig, audioDraft)
    }

    // 配置自检（守卫）：字段级校验通过后仍不可执行的组合 / 必填缺失 → 拦下并定位请求模板
    if (capability.level === 'needs_adapter') {
      setTab('request')
      toast.error(
        capability.issues.find((issue) => issue.severity === 'error')?.message ??
          '当前配置无法由通用驱动执行'
      )
      return
    }

    // 新建态：参数配置草稿随创建一起提交（空草稿不发，避免无意义的覆盖请求）
    const paramDraftHasContent =
      paramConfigDraft != null &&
      (paramConfigDraft.params.length > 0 || paramConfigDraft.mappings.length > 0)
    const paramOverrides =
      api?.id == null && paramDraftHasContent && paramConfigDraft
        ? { algorithmType: values.algorithmType, ...paramConfigDraft }
        : undefined

    // INT-1939：只有保存成功才关闭弹窗；失败时 toast 已由 useApisCrud 给出，
    // 弹窗与五个页签草稿原样保留，保存钮恢复可点，可在弹窗内直接重试。
    if (await save(payload, paramOverrides)) onOpenChange(false)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
      {/* 参数配置页签的表格列多（代码/名称/类型/方向/排序/响应路径），2xl 会横向裁切 */}
      <DialogContent className='sm:max-w-5xl'>
        <DialogHeader>
          <DialogTitle>{api ? '编辑 API' : '新增 API'}</DialogTitle>
          <DialogDescription>
            {api ? '修改被测 API 配置，保存后列表自动刷新' : '新增被测 API，保存后列表自动刷新'}
          </DialogDescription>
        </DialogHeader>

        {/* INT-1939 / A3：校验统一走 zod + 各页签字段级校验（中文内联提示，定位到控件），
            noValidate 关掉浏览器原生校验气泡，不让它盖掉同口径提示 */}
        <form
          noValidate
          onSubmit={form.handleSubmit(handleSave)}
          className='flex min-h-0 flex-col gap-3'
        >
          <Tabs
            value={tab}
            onValueChange={(value) => setTab(value as ApiTab)}
            className='min-h-0'
          >
            <TabsList variant='line' className='w-full justify-start gap-1 overflow-x-auto'>
              {API_TABS.map((item) => (
                <TabsTrigger key={item.value} value={item.value} className='flex-none px-2.5'>
                  {item.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <div className='max-h-[58vh] min-h-[22rem] overflow-y-auto pr-1'>
              {/* 基础页签：现有字段口径不变 + audio_config 编辑区（顶层列） */}
              <TabsContent value='basic' className='space-y-3'>
                <div className='space-y-1.5'>
                  <Label htmlFor='api-name'>API 名称 *</Label>
                  <Input
                    id='api-name'
                    placeholder='请输入 API 名称'
                    aria-invalid={Boolean(form.formState.errors.name)}
                    {...form.register('name')}
                  />
                  {form.formState.errors.name && (
                    <p className='text-destructive text-xs'>{form.formState.errors.name.message}</p>
                  )}
                </div>

                <div className='space-y-1.5'>
                  <Label>关联算法 *</Label>
                  <Select
                    value={form.watch('algorithmType')}
                    // 收起态靠 items 取 label（INT-1633 同口径）；漏传会直接回显算法类型码
                    items={algorithmList.map((algorithm) => ({ value: algorithm.id, label: algorithm.name }))}
                    onValueChange={(value) => form.setValue('algorithmType', value ?? '')}
                  >
                    <SelectTrigger className={cn('w-full justify-between', !form.watch('algorithmType') && 'text-muted-foreground')}>
                      <SelectValue placeholder='请选择算法' />
                    </SelectTrigger>
                    <SelectContent>
                      {algorithmList.map((algorithm) => (
                        <SelectItem key={algorithm.id} value={algorithm.id}>
                          {algorithm.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {form.formState.errors.algorithmType && (
                    <p className='text-destructive text-xs'>{form.formState.errors.algorithmType.message}</p>
                  )}
                </div>

                <div className='space-y-1.5'>
                  <Label htmlFor='max-process'>最大并发（所有端点合计）</Label>
                  <Input
                    id='max-process'
                    type='number'
                    min={1}
                    max={128}
                    aria-invalid={Boolean(form.formState.errors.maxProcess)}
                    {...form.register('maxProcess', { valueAsNumber: true })}
                  />
                  {form.formState.errors.maxProcess ? (
                    <p className='text-destructive text-xs'>
                      {form.formState.errors.maxProcess.message}
                    </p>
                  ) : (
                    <p className='text-muted-foreground text-xs'>
                      本 API 下所有端点共享的总并发上限；单个端点自己的上限在下方端点行「端点最大并发」。
                    </p>
                  )}
                </div>

                {/* 协议 × 流式性（INT-1800 / B0 §3.2）：两个独立维度，不互相推断。
                    协议下拉 4 值均已上线；流式开关按可用矩阵锁定（仅 sse 锁流式）。 */}
                <div className='space-y-1.5'>
                  <Label>协议 *</Label>
                  <Select
                    value={watchedProtocol}
                    items={PROTOCOL_OPTIONS.map((option) => ({
                      value: option.value,
                      label: option.disabled ? `${option.label}（未上线）` : option.label,
                    }))}
                    onValueChange={(value) => {
                      if (!isApiProtocol(value)) return
                      form.setValue('protocol', value)
                      // 切协议即按该协议的缺省流式性联动（可用矩阵内只有一种可写形态）
                      form.setValue('streaming', defaultStreamingFor(value))
                    }}
                  >
                    <SelectTrigger className='w-full justify-between' aria-label='协议'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PROTOCOL_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
                          {API_PROTOCOL_LABEL[option.value]}
                          {option.disabled && (
                            <span className='text-muted-foreground ml-1 text-xs'>（未上线）</span>
                          )}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className='text-muted-foreground text-xs'>
                    协议只存规范值（http / websocket / sse / grpc）；除 SSE 仅支持流式外，
                    其余协议的流式性由下方开关决定，不由协议推断。
                  </p>
                </div>

                <div className='space-y-1.5'>
                  <div className='flex items-center justify-between gap-2'>
                    <Label htmlFor='api-streaming'>流式性</Label>
                    <div className='flex items-center gap-2'>
                      <span className='text-muted-foreground text-xs'>
                        {watchedStreaming ? '实时（流式）' : '请求-响应（非流式）'}
                      </span>
                      <Switch
                        id='api-streaming'
                        size='sm'
                        checked={watchedStreaming}
                        disabled={streamingLocked}
                        onCheckedChange={(checked) => form.setValue('streaming', checked)}
                        aria-label='流式开关'
                      />
                    </div>
                  </div>
                  {streamingLocked ? (
                    <p className='text-muted-foreground text-xs'>
                      {API_PROTOCOL_LABEL[watchedProtocol] ?? '该协议'}只支持
                      {streamingLabel(defaultStreamingFor(watchedProtocol))} 一种形态，开关锁定；
                      需要另一种形态请改用 HTTP / WebSocket / gRPC。
                    </p>
                  ) : (
                    <p className='text-muted-foreground text-xs'>
                      流式 = 实时（会话/轮次语义），非流式 = 请求-响应；执行道只由这里决定，与协议无关。
                    </p>
                  )}
                  {combinationWarning && (
                    <p className='text-destructive text-xs'>
                      {combinationWarning}：该组合保存会被后端拒绝（400）。
                    </p>
                  )}
                </div>

                <div className='space-y-1.5'>
                  <Label htmlFor='api-desc'>描述</Label>
                  <Textarea id='api-desc' rows={2} placeholder='API 用途说明（可选）' {...form.register('description')} />
                </div>

                {/* INT-1777 audio_config（顶层列 apis.audio_config，不是 meta.audio_config）；
                    INT-1771：输入 / 输出两套格式分开配置（可不同） */}
                <div className='border-border/60 space-y-3 rounded-lg border p-3'>
                  <div className='flex flex-wrap items-start justify-between gap-2'>
                    <div>
                      <Label>音频格式（audio_config）</Label>
                      <p className='text-muted-foreground text-xs'>
                        输入（下发）与输出（回传）可以不同；未配置时运行时回退 24000Hz / s16 / 单声道 / pcm。
                      </p>
                    </div>
                    <Button
                      type='button'
                      variant='outline'
                      size='sm'
                      className='h-7 text-xs'
                      onClick={clearAudioConfig}
                    >
                      清除音频格式
                    </Button>
                  </div>
                  <div className='grid grid-cols-1 gap-3 md:grid-cols-2'>
                    {AUDIO_DIRECTION_FIELDS.map((direction) => (
                      <div
                        key={direction.key}
                        className='border-border/40 space-y-2 rounded-md border p-2.5'
                      >
                        <AudioFormatFields
                          label={direction.label}
                          hint={direction.hint}
                          value={audioDraft[direction.key]}
                          onChange={(patch) => updateAudio(direction.key, patch)}
                        />
                      </div>
                    ))}
                  </div>
                  <p className='text-muted-foreground text-xs'>
                    {audioCleared
                      ? '保存后将清空 audio_config（提交 {}）。'
                      : '未改动时不提交 audio_config；某一侧四项全空则删除该侧（执行侧回退另一侧同值）。'}
                  </p>
                </div>

                {/* 端点列表（INT-1223：Master URL 移除后唯一端点入口——保证从开始测试页可新建含端点的 API） */}
                <div className='space-y-1.5'>
                  <div className='flex items-center justify-between'>
                    <Label>端点列表</Label>
                    <Button
                      type='button'
                      variant='outline'
                      size='sm'
                      className='h-7 gap-1 text-xs'
                      onClick={addEndpoint}
                    >
                      <Plus aria-hidden='true' className='size-3.5' />
                      添加端点
                    </Button>
                  </div>
                  {endpoints.length === 0 ? (
                    <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
                      暂无端点，点击「添加端点」配置（优先级/端点最大并发/超时/音频时长）
                    </p>
                  ) : (
                    <div className='flex flex-col gap-2'>
                      {endpoints.map((row) => (
                        <div key={row.key} className='border-border/60 flex flex-col gap-1.5 rounded-lg border p-2'>
                          <div className='flex items-center gap-1.5'>
                            <Input
                              value={row.endpoint}
                              onChange={(e) => updateEndpoint(row.key, { endpoint: e.target.value })}
                              placeholder='https://…'
                              className='h-7 flex-1 font-mono text-xs'
                              aria-label='端点 URL'
                            />
                            <Button
                              type='button'
                              variant='ghost'
                              size='icon-sm'
                              className='size-6 text-destructive'
                              aria-label='删除端点'
                              onClick={() => removeEndpoint(row.key)}
                            >
                              <X aria-hidden='true' className='size-3.5' />
                            </Button>
                          </div>
                          {/* INT-2153：端点行常驻标签（原实现只有 placeholder，填值后看不出这列是什么）；
                              标签与后端四整数校验项一一对应，错误提示仍逐字段落在输入框下方 */}
                          <div className='grid grid-cols-5 items-start gap-1.5'>
                            <div className='space-y-0.5'>
                              <Label className='text-muted-foreground text-[11px] font-normal'>
                                名称
                              </Label>
                              <Input
                                value={row.name}
                                onChange={(e) => updateEndpoint(row.key, { name: e.target.value })}
                                placeholder='可选'
                                aria-label='端点名称'
                                className='h-7 text-xs'
                              />
                            </div>
                            {/* INT-1939 返工：四项整数改由 validateEndpointNumbers 自查并给中文内联提示
                                （表单 noValidate 后原生 min/max 只是展示，不再拦截提交） */}
                            {ENDPOINT_NUMERIC_RULES.map((rule) => (
                              <div key={rule.field} className='space-y-0.5'>
                                <Label className='text-muted-foreground text-[11px] font-normal'>
                                  {rule.label}
                                </Label>
                                <Input
                                  value={row[rule.field]}
                                  type='number'
                                  min={rule.min}
                                  max={rule.max ?? undefined}
                                  aria-label={rule.ariaLabel}
                                  aria-invalid={Boolean(endpointErrorOf(row.key, rule.field))}
                                  onChange={(e) =>
                                    setEndpointNumber(row.key, rule.field, e.target.value)
                                  }
                                  placeholder={
                                    rule.max == null ? `≥${rule.min}` : `${rule.min}~${rule.max}`
                                  }
                                  className='h-7 text-xs'
                                />
                                {endpointErrorOf(row.key, rule.field) && (
                                  <p className='text-destructive text-xs'>
                                    {endpointErrorOf(row.key, rule.field)}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                          {/* INT-1437 密钥池：端点行内多行 textarea（每行一个 key，整段粘贴自动拆行）；
                              编辑回显只显示摘要（count + 尾号），完整密钥不出现 */}
                          <div className='space-y-1'>
                            <Label className='text-xs'>密钥池（多密钥轮换）</Label>
                            {row.apiKeysSummary && row.apiKeysSummary.count > 0 && (
                              <p className='text-muted-foreground text-xs'>
                                已配置 {row.apiKeysSummary.count} 个密钥
                                {row.apiKeysSummary.tails.length > 0 && (
                                  <>（尾号：{row.apiKeysSummary.tails.join('、')}）</>
                                )}
                                ，如需修改请重新输入完整密钥列表。
                              </p>
                            )}
                            <Textarea
                              rows={2}
                              value={row.apiKeysText}
                              onChange={(e) => updateEndpoint(row.key, { apiKeysText: e.target.value })}
                              placeholder='每行一个密钥，可整段粘贴自动拆行；留空则保留已配置密钥'
                              className='h-12 font-mono text-xs'
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </TabsContent>

              {/* 请求模板页签：写 meta，协议决定请求配置区、流式性决定轮次/会话配置区（旧键保留不删，只隐藏） */}
              <TabsContent value='request' className='space-y-3'>
                {/* 配置自检：说清「纯配置可跑」还是「缺什么」 */}
                <div
                  className={cn(
                    'rounded-lg border p-2.5 text-xs',
                    capability.level === 'needs_adapter'
                      ? 'border-destructive/40 bg-destructive/10'
                      : 'border-border/60 bg-muted/40'
                  )}
                >
                  <p className='font-medium'>
                    {capability.level === 'configurable'
                      ? '配置自检：当前配置可由通用驱动直接执行（无需代码适配器）'
                      : '配置自检：还有必填项缺失，保存后无法执行'}
                  </p>
                  {capability.issues.length > 0 && (
                    <ul className='text-muted-foreground mt-1 list-disc space-y-0.5 pl-4'>
                      {capability.issues.map((issue) => (
                        <li
                          key={issue.message}
                          className={issue.severity === 'error' ? 'text-destructive' : undefined}
                        >
                          {issue.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className='bg-muted/40 text-muted-foreground rounded-lg border p-2.5 text-xs'>
                  按协议与流式性显隐，当前：
                  <Badge variant='secondary' className='mx-1'>
                    {watchedProtocol ? API_PROTOCOL_LABEL[watchedProtocol] : '—'}
                  </Badge>
                  <Badge variant='secondary' className='mr-1'>
                    {streamingLabel(watchedStreaming)}
                  </Badge>
                  切换协议 / 流式性后旧键保留不删，只隐藏；切回即恢复。
                </div>

                {isWebSocket && (
                  <KeyValueEditor
                    label='WS 请求头'
                    addLabel='添加请求头'
                    emptyHint='未配置 WS 请求头'
                    rows={metaDraft.wsHeaders}
                    error={metaErrorOf('wsHeaders')}
                    onChange={(rows) => updateMeta({ wsHeaders: rows })}
                  />
                )}

                {watchedProtocol === 'http' && (
                  <>
                    <div className='space-y-1.5'>
                      <Label>请求方法（method）</Label>
                      <Select
                        value={metaDraft.method || UNSET}
                        items={METHOD_OPTIONS}
                        onValueChange={(value) =>
                          updateMeta({ method: value && value !== UNSET ? value : '' })
                        }
                      >
                        <SelectTrigger className='w-full justify-between'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={UNSET}>未设置</SelectItem>
                          {HTTP_METHOD_OPTIONS.map((method) => (
                            <SelectItem key={method} value={method}>
                              {method}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <KeyValueEditor
                      label='请求头'
                      addLabel='添加请求头'
                      emptyHint='未配置请求头'
                      rows={metaDraft.headers}
                      error={metaErrorOf('headers')}
                      onChange={(rows) => updateMeta({ headers: rows })}
                    />
                    <SampleJsonImport
                      kind='request'
                      onApply={(text) => {
                        const result = inferBodyTemplate(text)
                        updateMeta({
                          bodyTemplateMode: 'json',
                          bodyTemplateText: result.templateText,
                        })
                        return result.audioPath
                          ? `已生成模板；音频字段 ${result.audioPath} 已替换为 {{audio_b64}}`
                          : '已生成请求模板'
                      }}
                    />
                    <div className='space-y-1.5'>
                      <div className='flex flex-wrap items-center justify-between gap-2'>
                        <Label htmlFor='meta-body-template'>请求体模板（body_template）</Label>
                        <Select
                          value={metaDraft.bodyTemplateMode}
                          items={BODY_TEMPLATE_MODE_OPTIONS}
                          onValueChange={(value) =>
                            updateMeta({ bodyTemplateMode: (value ?? 'json') as BodyTemplateMode })
                          }
                        >
                          <SelectTrigger size='sm' className='w-40 justify-between'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value='json'>结构化 JSON</SelectItem>
                            <SelectItem value='raw'>原始字符串模板</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <Textarea
                        id='meta-body-template'
                        rows={5}
                        value={metaDraft.bodyTemplateText}
                        onChange={(e) => updateMeta({ bodyTemplateText: e.target.value })}
                        placeholder={
                          metaDraft.bodyTemplateMode === 'json'
                            ? '{\n  "text": "{{text}}"\n}'
                            : '{"text":"${text}"} 等原始模板字符串（含占位符）'
                        }
                        className='font-mono text-xs'
                        aria-invalid={Boolean(metaErrorOf('bodyTemplate'))}
                      />
                      {metaErrorOf('bodyTemplate') ? (
                        <p className='text-destructive text-xs'>{metaErrorOf('bodyTemplate')}</p>
                      ) : (
                        <p className='text-muted-foreground text-xs'>
                          {metaDraft.bodyTemplateMode === 'json'
                            ? '结构化 JSON 对象，保存前校验格式。'
                            : '原始字符串模板（可含占位符），原样写入 meta.body_template。'}
                        </p>
                      )}
                    </div>
                  </>
                )}

                {/* gRPC 组（A3 §4.1）：proto 三元组 + service / method / method_kind +
                    metadata + deadline。执行侧 grpc_adapter / grpc_client 只读这几组键。 */}
                {watchedProtocol === 'grpc' && (
                  <div className='border-border/60 space-y-3 rounded-lg border p-3'>
                    <div className='flex flex-wrap items-start justify-between gap-2'>
                      <div>
                        <Label>gRPC 协议配置（meta.grpc）</Label>
                        <p className='text-muted-foreground text-xs'>
                          协议文件上传接口（
                          <code className='font-mono'>POST /api/v1/apis/proto</code>，INT-1952）
                          尚未上线（已交付、未部署）：上传暂不可用，下列 proto 键可手填。
                        </p>
                      </div>
                      <div className='flex flex-none items-center gap-1.5'>
                        <input
                          ref={protoFileRef}
                          type='file'
                          accept='.proto'
                          className='hidden'
                          aria-label='选择 .proto 文件'
                          onChange={handleProtoFile}
                        />
                        <Button
                          type='button'
                          variant='outline'
                          size='sm'
                          className='h-7 gap-1 text-xs'
                          disabled={protoUploading}
                          onClick={() => protoFileRef.current?.click()}
                        >
                          <Upload aria-hidden='true' className='size-3.5' />
                          {protoUploading ? '上传中…' : '上传 .proto'}
                        </Button>
                      </div>
                    </div>
                    {protoUploadError && (
                      <p className='text-destructive text-xs'>上传失败：{protoUploadError}</p>
                    )}

                    <div className='grid grid-cols-1 gap-2 sm:grid-cols-3'>
                      <div className='space-y-1'>
                        <Label className='text-xs'>proto_object_key *</Label>
                        <Input
                          value={metaDraft.grpcProtoObjectKey}
                          onChange={(e) => updateMeta({ grpcProtoObjectKey: e.target.value })}
                          placeholder={'api-protos/<sha256>.proto'}
                          className='h-7 font-mono text-xs'
                          aria-label='proto_object_key'
                          aria-invalid={Boolean(metaErrorOf('grpcProto'))}
                        />
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>proto_sha256</Label>
                        <Input
                          value={metaDraft.grpcProtoSha256}
                          onChange={(e) => updateMeta({ grpcProtoSha256: e.target.value })}
                          placeholder='64 位小写十六进制'
                          className='h-7 font-mono text-xs'
                          aria-label='proto_sha256'
                          aria-invalid={Boolean(metaErrorOf('grpcProto'))}
                        />
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>proto_size（字节）</Label>
                        <Input
                          type='number'
                          min={1}
                          max={256 * 1024}
                          value={metaDraft.grpcProtoSize}
                          onChange={(e) => updateMeta({ grpcProtoSize: e.target.value })}
                          placeholder='≤ 262144'
                          className='h-7 font-mono text-xs'
                          aria-label='proto_size'
                          aria-invalid={Boolean(metaErrorOf('grpcProto'))}
                        />
                      </div>
                    </div>
                    {metaErrorOf('grpcProto') && (
                      <p className='text-destructive text-xs'>{metaErrorOf('grpcProto')}</p>
                    )}

                    <div className='grid grid-cols-2 gap-2'>
                      <div className='space-y-1'>
                        <Label className='text-xs'>service *</Label>
                        {protoSymbols ? (
                          <Select
                            value={metaDraft.grpcService || UNSET}
                            items={[UNSET_OPTION, ...grpcServiceOptions]}
                            onValueChange={(value) =>
                              updateMeta({
                                grpcService: value && value !== UNSET ? value : '',
                                // 换 service → method 清空（方法名只在所属 service 内有意义）
                                grpcMethod: '',
                                grpcMethodKind: '',
                              })
                            }
                          >
                            <SelectTrigger className='w-full justify-between' aria-label='service'>
                              <SelectValue placeholder='请选择 service' />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={UNSET}>未设置</SelectItem>
                              {grpcServiceOptions.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            value={metaDraft.grpcService}
                            onChange={(e) => updateMeta({ grpcService: e.target.value })}
                            placeholder='手填 proto 里的 service 全名'
                            className='h-7 font-mono text-xs'
                            aria-label='service'
                            aria-invalid={Boolean(metaErrorOf('grpcService'))}
                          />
                        )}
                        {metaErrorOf('grpcService') && (
                          <p className='text-destructive text-xs'>{metaErrorOf('grpcService')}</p>
                        )}
                      </div>
                      <div className='space-y-1'>
                        <Label className='text-xs'>method *</Label>
                        {protoSymbols ? (
                          <Select
                            value={metaDraft.grpcMethod || UNSET}
                            items={[UNSET_OPTION, ...grpcMethodOptions]}
                            onValueChange={(value) => {
                              const methodName = value && value !== UNSET ? value : ''
                              const symbol =
                                grpcServiceSymbol?.methods.find((m) => m.name === methodName) ?? null
                              updateMeta({
                                grpcMethod: methodName,
                                // method_kind 缺省取符号表推断值（执行期必须与 descriptor 一致）
                                grpcMethodKind: symbol?.methodKind ?? '',
                              })
                            }}
                          >
                            <SelectTrigger className='w-full justify-between' aria-label='method'>
                              <SelectValue placeholder='请选择 method' />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={UNSET}>未设置</SelectItem>
                              {grpcMethodOptions.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            value={metaDraft.grpcMethod}
                            onChange={(e) => updateMeta({ grpcMethod: e.target.value })}
                            placeholder='手填方法名'
                            className='h-7 font-mono text-xs'
                            aria-label='method'
                            aria-invalid={Boolean(metaErrorOf('grpcMethod'))}
                          />
                        )}
                        {metaErrorOf('grpcMethod') && (
                          <p className='text-destructive text-xs'>{metaErrorOf('grpcMethod')}</p>
                        )}
                      </div>
                    </div>

                    <div className='space-y-1'>
                      <Label className='text-xs'>method_kind *</Label>
                      <Select
                        value={metaDraft.grpcMethodKind || UNSET}
                        items={GRPC_METHOD_KIND_OPTIONS}
                        onValueChange={(value) =>
                          updateMeta({
                            grpcMethodKind: value && value !== UNSET ? value : '',
                          })
                        }
                      >
                        <SelectTrigger className='w-full justify-between' aria-label='method_kind'>
                          <SelectValue placeholder='unary / server_stream / bidi' />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={UNSET}>未设置</SelectItem>
                          {GRPC_METHOD_KINDS.map((kind) => (
                            <SelectItem key={kind} value={kind}>
                              {kind === 'unary'
                                ? 'unary（一元）'
                                : kind === 'server_stream'
                                  ? 'server_stream（服务端流）'
                                  : 'bidi（双向流）'}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {metaErrorOf('grpcMethodKind') ? (
                        <p className='text-destructive text-xs'>{metaErrorOf('grpcMethodKind')}</p>
                      ) : grpcMethodSymbol &&
                        metaDraft.grpcMethodKind &&
                        metaDraft.grpcMethodKind !== grpcMethodSymbol.methodKind ? (
                        <p className='text-xs text-amber-600 dark:text-amber-400'>
                          与 proto 声明（{grpcMethodSymbol.methodKind}）不一致：执行期会抛
                          GrpcMethodKindError，请确认后再保存。
                        </p>
                      ) : (
                        <p className='text-muted-foreground text-xs'>
                          须与 proto descriptor 一致；上传 .proto 后自动取符号表推断值。
                        </p>
                      )}
                    </div>

                    {grpcMethodSymbol && (
                      <div className='grid grid-cols-2 gap-2'>
                        <ProtoFieldList
                          title={`请求消息（${grpcMethodSymbol.inputType}）`}
                          fields={grpcMethodSymbol.inputFields}
                        />
                        <ProtoFieldList
                          title={`响应消息（${grpcMethodSymbol.outputType}）`}
                          fields={grpcMethodSymbol.outputFields}
                        />
                      </div>
                    )}

                    <KeyValueEditor
                      label='metadata（键必须小写）'
                      addLabel='添加 metadata'
                      emptyHint='未配置 metadata'
                      rows={metaDraft.grpcMetadata}
                      error={metaErrorOf('grpcMetadata')}
                      secretKeys={GRPC_METADATA_SECRET_KEYS}
                      onChange={(rows) => updateMeta({ grpcMetadata: rows })}
                    />
                    <p className='text-muted-foreground text-xs'>
                      值支持 <code className='font-mono'>{'{{placeholder}}'}</code> 占位；
                      鉴权值当前明文存储 / 回显，脱敏待 INT-1953。
                    </p>

                    <div className='space-y-1'>
                      <Label htmlFor='grpc-deadline' className='text-xs'>
                        deadline_ms（毫秒）
                      </Label>
                      <Input
                        id='grpc-deadline'
                        type='number'
                        min={1}
                        value={metaDraft.grpcDeadlineMs}
                        onChange={(e) => updateMeta({ grpcDeadlineMs: e.target.value })}
                        placeholder={grpcDeadlinePlaceholder}
                        className='h-7 text-xs'
                        aria-invalid={Boolean(metaErrorOf('grpcDeadlineMs'))}
                      />
                      {metaErrorOf('grpcDeadlineMs') ? (
                        <p className='text-destructive text-xs'>{metaErrorOf('grpcDeadlineMs')}</p>
                      ) : (
                        <p className='text-muted-foreground text-xs'>
                          正整数；留空 = 端点超时 × 1000。
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* SSE 组（A3 §4.2 = 01 契约 §11.2）：只显示 method / headers + SSE 键；
                    请求载荷统一 meta.sse.params，**不显示 body_template**
                    （A2 执行侧 protocol == 'sse' 时从不读它）。 */}
                {watchedProtocol === 'sse' && (
                  <div className='border-border/60 space-y-3 rounded-lg border p-3'>
                    <div>
                      <Label>SSE 协议配置（meta.sse）</Label>
                      <p className='text-muted-foreground text-xs'>
                        请求载荷统一由 params 决定（GET 走 query string、非 GET 走 JSON body）；
                        SSE 不使用请求体模板，因此本组不显示 body_template。
                      </p>
                    </div>

                    <div className='grid grid-cols-2 gap-2'>
                      <div className='space-y-1'>
                        <Label className='text-xs'>请求方法（method，缺省 GET）</Label>
                        <Select
                          value={metaDraft.method || UNSET}
                          items={METHOD_OPTIONS}
                          onValueChange={(value) =>
                            updateMeta({ method: value && value !== UNSET ? value : '' })
                          }
                        >
                          <SelectTrigger
                            className='w-full justify-between'
                            aria-label='SSE 请求方法'
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={UNSET}>未设置（缺省 GET）</SelectItem>
                            {HTTP_METHOD_OPTIONS.map((method) => (
                              <SelectItem key={method} value={method}>
                                {method}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className='space-y-1'>
                        <Label htmlFor='sse-event-name-field' className='text-xs'>
                          事件名字段（event_name_field）
                        </Label>
                        <Input
                          id='sse-event-name-field'
                          value={metaDraft.sseEventNameField}
                          onChange={(e) => updateMeta({ sseEventNameField: e.target.value })}
                          placeholder={`留空 = 缺省 ${SSE_DEFAULTS.eventNameField}`}
                          className='h-7 font-mono text-xs'
                          aria-invalid={Boolean(metaErrorOf('sseEventNameField'))}
                        />
                        {metaErrorOf('sseEventNameField') && (
                          <p className='text-destructive text-xs'>
                            {metaErrorOf('sseEventNameField')}
                          </p>
                        )}
                      </div>
                    </div>

                    <KeyValueEditor
                      label='请求头（与 HTTP 组共用 meta.headers）'
                      addLabel='添加请求头'
                      emptyHint='未配置请求头'
                      rows={metaDraft.headers}
                      error={metaErrorOf('headers')}
                      onChange={(rows) => updateMeta({ headers: rows })}
                    />

                    <KeyValueEditor
                      label='请求参数（params）'
                      addLabel='添加参数'
                      emptyHint='未配置请求参数'
                      rows={metaDraft.sseParams}
                      error={metaErrorOf('sseParams')}
                      onChange={(rows) => updateMeta({ sseParams: rows })}
                    />

                    <div className='space-y-1.5'>
                      <div className='flex items-center justify-between gap-2'>
                        <div>
                          <Label htmlFor='sse-reconnect'>断流重连（reconnect_enabled）</Label>
                          <p className='text-muted-foreground text-xs'>
                            缺省不重连：断流即失败，重连会让轮次数不可复现。
                          </p>
                        </div>
                        <Switch
                          id='sse-reconnect'
                          size='sm'
                          checked={metaDraft.sseReconnectEnabled}
                          onCheckedChange={(checked) =>
                            updateMeta({ sseReconnectEnabled: checked })
                          }
                          aria-label='SSE 重连开关'
                        />
                      </div>
                      <div className='space-y-1'>
                        <Label htmlFor='sse-reconnect-attempts' className='text-xs'>
                          重连次数上限（max_reconnect_attempts）
                        </Label>
                        <Input
                          id='sse-reconnect-attempts'
                          type='number'
                          min={SSE_FIELD_LIMITS.maxReconnectAttempts.min}
                          max={SSE_FIELD_LIMITS.maxReconnectAttempts.max}
                          disabled={!metaDraft.sseReconnectEnabled}
                          value={metaDraft.sseMaxReconnectAttempts}
                          onChange={(e) =>
                            updateMeta({ sseMaxReconnectAttempts: e.target.value })
                          }
                          placeholder={`留空 = 缺省 ${SSE_DEFAULTS.maxReconnectAttempts}（0-10）`}
                          className='h-7 text-xs'
                          aria-invalid={Boolean(metaErrorOf('sseMaxReconnectAttempts'))}
                        />
                        {metaErrorOf('sseMaxReconnectAttempts') && (
                          <p className='text-destructive text-xs'>
                            {metaErrorOf('sseMaxReconnectAttempts')}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className='grid grid-cols-3 gap-2'>
                      <div className='space-y-1'>
                        <Label htmlFor='sse-retry' className='text-xs'>
                          重连退避上限（retry_ms）
                        </Label>
                        <Input
                          id='sse-retry'
                          type='number'
                          min={SSE_FIELD_LIMITS.retryMs.min}
                          max={SSE_FIELD_LIMITS.retryMs.max}
                          value={metaDraft.sseRetryMs}
                          onChange={(e) => updateMeta({ sseRetryMs: e.target.value })}
                          placeholder={`留空 = ${SSE_DEFAULTS.retryMs}（0-60000）`}
                          className='h-7 text-xs'
                          aria-invalid={Boolean(metaErrorOf('sseRetryMs'))}
                        />
                        {metaErrorOf('sseRetryMs') && (
                          <p className='text-destructive text-xs'>{metaErrorOf('sseRetryMs')}</p>
                        )}
                      </div>
                      <div className='space-y-1'>
                        <Label htmlFor='sse-idle' className='text-xs'>
                          空闲超时（idle_timeout_ms）
                        </Label>
                        <Input
                          id='sse-idle'
                          type='number'
                          min={SSE_FIELD_LIMITS.idleTimeoutMs.min}
                          max={SSE_FIELD_LIMITS.idleTimeoutMs.max}
                          value={metaDraft.sseIdleTimeoutMs}
                          onChange={(e) => updateMeta({ sseIdleTimeoutMs: e.target.value })}
                          placeholder={sseIdlePlaceholder}
                          className='h-7 text-xs'
                          aria-invalid={Boolean(metaErrorOf('sseIdleTimeoutMs'))}
                        />
                        {metaErrorOf('sseIdleTimeoutMs') && (
                          <p className='text-destructive text-xs'>
                            {metaErrorOf('sseIdleTimeoutMs')}
                          </p>
                        )}
                      </div>
                      <div className='space-y-1'>
                        <Label htmlFor='sse-duration' className='text-xs'>
                          整体时长上限（max_duration_ms）
                        </Label>
                        <Input
                          id='sse-duration'
                          type='number'
                          min={SSE_FIELD_LIMITS.maxDurationMs.min}
                          max={SSE_FIELD_LIMITS.maxDurationMs.max}
                          value={metaDraft.sseMaxDurationMs}
                          onChange={(e) => updateMeta({ sseMaxDurationMs: e.target.value })}
                          placeholder='留空 = 不设上限'
                          className='h-7 text-xs'
                          aria-invalid={Boolean(metaErrorOf('sseMaxDurationMs'))}
                        />
                        {metaErrorOf('sseMaxDurationMs') && (
                          <p className='text-destructive text-xs'>
                            {metaErrorOf('sseMaxDurationMs')}
                          </p>
                        )}
                      </div>
                    </div>

                    <p className='text-muted-foreground text-xs'>
                      句子结束 / 会话结束标记在「响应解析」页签（sentence_end_mapping /
                      session_end_mapping），本组不重复声明同名键。
                    </p>
                  </div>
                )}

                {/* 轮次 / 会话配置区：只由流式性决定（B0 §3.5；非流式无会话概念），
                    且只有 HTTP / WS 两条执行道读这组键（SSE / gRPC 各有自己的载荷口径） */}
                {watchedStreaming && (isWebSocket || watchedProtocol === 'http') && (
                  <>
                    <Separator />
                    <JsonTextarea
                      id='meta-session-config'
                      label='会话配置（session_config）'
                      hint='JSON 对象，如 {"turn_detection": true}'
                      value={metaDraft.sessionConfig}
                      error={metaErrorOf('sessionConfig')}
                      onChange={(text) => updateMeta({ sessionConfig: text })}
                    />
                    <JsonTextarea
                      id='meta-pacing'
                      label='节奏控制（pacing）'
                      hint='JSON 对象，如 {"interval_ms": 200}'
                      value={metaDraft.pacing}
                      error={metaErrorOf('pacing')}
                      onChange={(text) => updateMeta({ pacing: text })}
                    />
                  </>
                )}

                {/* WS 流式两段载荷（Qwen live-translate 方言）：首帧建连后一次、音频帧每 100ms。
                    关闭开关即回落执行侧默认（session.update / input_audio_buffer.append）。 */}
                {watchedStreaming && isWebSocket && (
                  <div className='border-border/60 space-y-3 rounded-lg border p-3'>
                    <div>
                      <p className='text-sm font-medium'>WS 载荷模板</p>
                      <p className='text-muted-foreground text-xs'>
                        首帧与音频帧是两种载荷：首帧只发一次，音频帧按 100ms 持续发。
                        首帧占位符取自会话配置的键；音频帧可用 {'{{audio_b64}}'} / {'{{event_id}}'}。
                      </p>
                    </div>
                    <div className='flex items-center justify-between gap-2'>
                      <Label htmlFor='meta-first-frame'>自定义首帧载荷（first_frame）</Label>
                      <Switch
                        id='meta-first-frame'
                        size='sm'
                        checked={metaDraft.firstFrameEnabled}
                        onCheckedChange={(checked) =>
                          updateMeta({ firstFrameEnabled: checked })
                        }
                        aria-label='自定义首帧载荷'
                      />
                    </div>
                    {metaDraft.firstFrameEnabled && (
                      <JsonTextarea
                        id='meta-first-frame-template'
                        label='首帧模板'
                        hint={FIRST_FRAME_HINT}
                        value={metaDraft.firstFrameTemplate}
                        error={metaErrorOf('firstFrameTemplate')}
                        onChange={(text) => updateMeta({ firstFrameTemplate: text })}
                      />
                    )}
                    <div className='flex items-center justify-between gap-2'>
                      <Label htmlFor='meta-audio-frame'>自定义音频帧载荷（audio_frame）</Label>
                      <Switch
                        id='meta-audio-frame'
                        size='sm'
                        checked={metaDraft.audioFrameEnabled}
                        onCheckedChange={(checked) =>
                          updateMeta({ audioFrameEnabled: checked })
                        }
                        aria-label='自定义音频帧载荷'
                      />
                    </div>
                    {metaDraft.audioFrameEnabled && (
                      <JsonTextarea
                        id='meta-audio-frame-template'
                        label='音频帧模板'
                        hint={AUDIO_FRAME_HINT}
                        value={metaDraft.audioFrameTemplate}
                        error={metaErrorOf('audioFrameTemplate')}
                        onChange={(text) => updateMeta({ audioFrameTemplate: text })}
                      />
                    )}
                  </div>
                )}

                <Separator />
                <div className='space-y-1.5'>
                  <Label htmlFor='meta-vendor-adapter'>厂商适配器（vendor_adapter）</Label>
                  <Select
                    value={metaDraft.vendorAdapter.trim() || UNSET}
                    items={vendorAdapterOptions}
                    onValueChange={(value) =>
                      updateMeta({ vendorAdapter: !value || value === UNSET ? '' : value })
                    }
                  >
                    <SelectTrigger
                      id='meta-vendor-adapter'
                      className='w-full justify-between'
                      aria-label='厂商适配器'
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {vendorAdapterOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className='text-muted-foreground text-xs'>
                    {
                      (vendorAdapterOptions.find(
                        (option) => option.value === (metaDraft.vendorAdapter.trim() || UNSET)
                      ) ?? VENDOR_ADAPTER_OPTIONS[0]).hint
                    }
                  </p>
                </div>
              </TabsContent>

              {/* 响应解析页签（INT-1778 §2.3）：result_parser / append_mode 两键 */}
              <TabsContent value='response' className='space-y-3'>
                <div className='bg-muted/40 space-y-1.5 rounded-lg border p-2.5 text-xs'>
                  <p className='flex flex-wrap items-center gap-1.5 font-medium'>
                    解析兜底口径（C0 裁定口径 · INT-1745）
                    <Badge variant='secondary' className='font-normal'>
                      {c0Status}
                    </Badge>
                  </p>
                  <p className='text-muted-foreground'>
                    按 C0 裁定口径：本页 meta 解析器只在该 API
                    <span className='text-foreground font-medium'>零输出字段声明</span>
                    时逐键兜底 —— 判定方式是同一次{' '}
                    <code className='font-mono'>
                      GET /algorithm/params?algorithm_type=…&amp;param_type=api&amp;api_id=…
                    </code>{' '}
                    没有 <code className='font-mono'>direction=output</code> 行；该 API（策略 + 实例覆盖）
                    声明了输出字段时，解析以「参数配置」页签的输出字段为准，本页解析器不作兜底，两者不按字段混用。
                  </p>
                </div>

                <SampleJsonImport
                  kind='response'
                  onApply={(text) => {
                    const result = inferResponseParser(text)
                    updateResponse({ resultParser: result.parserText })
                    return `识别到 ${result.fields
                      .map((field) => `${field.code} ← ${field.path}`)
                      .join('；')}`
                  }}
                />

                <div className='space-y-1.5'>
                  <Label htmlFor='meta-result-parser'>响应解析器（result_parser）</Label>
                  <Textarea
                    id='meta-result-parser'
                    rows={4}
                    value={responseDraft.resultParser}
                    onChange={(e) => updateResponse({ resultParser: e.target.value })}
                    placeholder={
                      '{\n  "asr_text_path": "data.text",\n  "trans_text_path": "data.translation",\n  "session_id_path": "data.session_id"\n}'
                    }
                    className='font-mono text-xs'
                    aria-invalid={Boolean(responseErrorOf('resultParser'))}
                  />
                  {responseErrorOf('resultParser') ? (
                    <p className='text-destructive text-xs'>{responseErrorOf('resultParser')}</p>
                  ) : (
                    <p className='text-muted-foreground text-xs'>
                      JSON 对象（键：asr_text_path / trans_text_path / session_id_path）；留空则不写入该键。
                    </p>
                  )}
                </div>

                {/* 负责人 2026-10-31 裁定：asr / trans / 句结束 / 会话结束 / 错误码 /
                    错误信息 6 个 *_mapping 由后端内置缺省即可，UI 不再暴露
                    （存量 meta 里的这些键原样保留，不读不写不删）。 */}

                <div className='space-y-1.5'>
                  <Label>流式结果拼接（append_mode）</Label>
                  <Select
                    value={responseDraft.appendMode || UNSET}
                    items={APPEND_MODE_OPTIONS}
                    onValueChange={(value) =>
                      updateResponse({
                        appendMode: (value && value !== UNSET ? value : '') as AppendModeValue,
                      })
                    }
                  >
                    <SelectTrigger
                      className='w-full justify-between'
                      aria-label='流式结果拼接（append_mode）'
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={UNSET}>未设置（按缺省：流式取最后一条）</SelectItem>
                      <SelectItem value='true'>是（逐句结束追加拼接）</SelectItem>
                      <SelectItem value='false'>否（保留最后一条分片）</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className='text-muted-foreground text-xs'>
                    仅流式（Realtime WS）响应生效：是 = 只拼接标记为句结束的分片；否 = 保留最后一条分片。
                  </p>
                </div>

                {/* 测试解析（A3 §二.4）：首次在 React 侧接上 POST /apis/parse-preview（INT-1772），
                    按当前协议换示例文案；用当前草稿里的解析器 / 映射直接试算。 */}
                <Separator />
                <ParsePreviewPanel protocol={watchedProtocol} draft={responseDraft} />
              </TabsContent>

              {/* 参数配置页签（T4.2）：API 实例作用域，策略绑定 + 输出字段 / 映射可编辑 + 覆盖保存。
                  keepMounted：切页签不卸载，行草稿与「未保存」标记都不丢。 */}
              <TabsContent value='param' className='space-y-3' keepMounted>
                <ApiParamConfigTab
                  apiId={api?.id ?? null}
                  algorithmType={algorithmType}
                  canEdit={canManageParams}
                  onDirtyChange={setParamConfigDirty}
                  onDraftChange={setParamConfigDraft}
                  derived={derivedFields}
                />
              </TabsContent>
            </div>
          </Tabs>

          {/* 配置策略：协议 / 流式 / 请求模板 / 响应解析 / 音频 / 参数与映射 整份存取（不含端点地址） */}
          <div className='bg-muted/30 flex flex-wrap items-center gap-2 rounded-lg border p-2'>
            <Label className='text-xs'>配置策略</Label>
            <Select
              value={applyProfileId || UNSET}
              items={[{ value: UNSET, label: '选择策略…' }, ...profileOptions]}
              onValueChange={(value) =>
                setApplyProfileId(!value || value === UNSET ? '' : value)
              }
              disabled={!algorithmType}
            >
              <SelectTrigger size='sm' className='w-52' aria-label='配置策略'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={UNSET}>选择策略…</SelectItem>
                {profileOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type='button'
              size='sm'
              variant='outline'
              className='h-7 text-xs'
              disabled={!applyProfileId}
              onClick={() => void applyStrategy()}
            >
              套用配置
            </Button>
            <Button
              type='button'
              size='sm'
              variant='outline'
              className='h-7 text-xs'
              disabled={!algorithmType}
              onClick={() => {
                setStrategyName('')
                setStrategyDialogOpen(true)
              }}
            >
              存为策略
            </Button>
            <span className='text-muted-foreground ml-auto text-xs'>
              策略含协议 / 请求模板 / 响应解析 / 音频 / 参数与映射；端点地址属实例私有不入策略。
            </span>
          </div>

          <DialogFooter>
            <Button variant='outline' type='button' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type='submit' disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
      </Dialog>

      {/* 存为配置策略：名称 + 说明（整份配置落 param_profiles.config_snapshot） */}
      <Dialog open={strategyDialogOpen} onOpenChange={setStrategyDialogOpen}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>存为配置策略</DialogTitle>
            <DialogDescription>
              保存当前协议 / 请求模板 / 响应解析 / 音频格式 / 参数与映射，供新建 API 时一键套用。
            </DialogDescription>
          </DialogHeader>
          <div className='space-y-2'>
            <Label htmlFor='api-strategy-name'>策略名称 *</Label>
            <Input
              id='api-strategy-name'
              value={strategyName}
              maxLength={100}
              placeholder='如：Qwen 实时翻译（WS）'
              onChange={(e) => setStrategyName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setStrategyDialogOpen(false)}>
              取消
            </Button>
            <Button type='button' disabled={strategySaving} onClick={() => void saveAsStrategy()}>
              {strategySaving ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/**
 * 一套音频格式四项（采样率 / 位深 / 通道数 / 容器）。
 * 输入侧与输出侧共用本组件，避免两份重复控件；aria-label 带上方向前缀便于定位。
 */
function AudioFormatFields({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint: string
  value: AudioFormatDraft
  onChange: (patch: Partial<AudioFormatDraft>) => void
}) {
  const pick = (raw: string) => (raw && raw !== UNSET ? raw : '')
  return (
    <div className='space-y-2'>
      <div>
        <Label className='text-xs font-medium'>{label}</Label>
        <p className='text-muted-foreground text-xs'>{hint}</p>
      </div>
      <div className='grid grid-cols-2 gap-2'>
        <div className='space-y-1'>
          <Label className='text-xs'>采样率</Label>
          <Select
            value={value.sampleRate || UNSET}
            items={SAMPLE_RATE_OPTIONS}
            onValueChange={(raw) => onChange({ sampleRate: pick(raw) })}
          >
            <SelectTrigger className='w-full justify-between' aria-label={`${label} 采样率`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={UNSET}>未设置</SelectItem>
              {AUDIO_SAMPLE_RATE_OPTIONS.map((rate) => (
                <SelectItem key={rate} value={String(rate)}>
                  {rate} Hz
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className='space-y-1'>
          <Label className='text-xs'>位深</Label>
          <Select
            value={value.bitDepth || UNSET}
            items={BIT_DEPTH_OPTIONS}
            onValueChange={(raw) => onChange({ bitDepth: pick(raw) })}
          >
            <SelectTrigger className='w-full justify-between' aria-label={`${label} 位深`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={UNSET}>未设置</SelectItem>
              {AUDIO_BIT_DEPTH_OPTIONS.map((depth) => (
                <SelectItem key={depth} value={depth}>
                  {depth}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className='space-y-1'>
          <Label className='text-xs'>通道数</Label>
          <Select
            value={value.channels || UNSET}
            items={CHANNEL_OPTIONS}
            onValueChange={(raw) => onChange({ channels: pick(raw) })}
          >
            <SelectTrigger className='w-full justify-between' aria-label={`${label} 通道数`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={UNSET}>未设置</SelectItem>
              {AUDIO_CHANNEL_OPTIONS.map((channel) => (
                <SelectItem key={channel} value={String(channel)}>
                  {channel === 1 ? '1（单声道）' : '2（立体声）'}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className='space-y-1'>
          <Label className='text-xs'>容器</Label>
          <Select
            value={value.container || UNSET}
            items={CONTAINER_OPTIONS}
            onValueChange={(raw) => onChange({ container: pick(raw) })}
          >
            <SelectTrigger className='w-full justify-between' aria-label={`${label} 容器`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={UNSET}>未设置</SelectItem>
              {AUDIO_CONTAINER_OPTIONS.map((container) => (
                <SelectItem key={container} value={container}>
                  {container}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  )
}

/** 键值表编辑器（headers / ws_headers / metadata / params；空行忽略，键名必填且不重复） */
function KeyValueEditor({
  label,
  addLabel,
  emptyHint,
  rows,
  error,
  secretKeys,
  onChange,
}: {
  label: string
  addLabel: string
  emptyHint: string
  rows: KeyValueRow[]
  error?: string
  /** 这些键名的值用密码控件输入（gRPC metadata 鉴权键；值本身仍明文存储，脱敏待 INT-1953） */
  secretKeys?: readonly string[]
  onChange: (rows: KeyValueRow[]) => void
}) {
  const patchRow = (id: string, patch: Partial<KeyValueRow>) =>
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  const isSecret = (key: string) =>
    Boolean(secretKeys?.length) &&
    (secretKeys as readonly string[]).includes(key.trim().toLowerCase())
  return (
    <div className='space-y-1.5'>
      <div className='flex items-center justify-between'>
        <Label>{label}</Label>
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='h-7 gap-1 text-xs'
          onClick={() => onChange([...rows, newKeyValueRow()])}
        >
          <Plus aria-hidden='true' className='size-3.5' />
          {addLabel}
        </Button>
      </div>
      {rows.length === 0 ? (
        <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
          {emptyHint}
        </p>
      ) : (
        <div className='flex flex-col gap-1.5'>
          {rows.map((row) => (
            <div key={row.id} className='flex items-center gap-1.5'>
              <Input
                value={row.key}
                onChange={(e) => patchRow(row.id, { key: e.target.value })}
                placeholder='名称'
                aria-label={`${label}名称`}
                className='h-7 flex-1 text-xs'
                aria-invalid={Boolean(error) && !row.key.trim()}
              />
              <Input
                value={row.value}
                onChange={(e) => patchRow(row.id, { value: e.target.value })}
                placeholder='值'
                aria-label={`${label}值`}
                type={isSecret(row.key) ? 'password' : 'text'}
                autoComplete='off'
                className='h-7 flex-1 text-xs'
              />
              <Button
                type='button'
                variant='ghost'
                size='icon-sm'
                className='size-6 text-destructive'
                aria-label={`删除${label}`}
                onClick={() => onChange(rows.filter((item) => item.id !== row.id))}
              >
                <X aria-hidden='true' className='size-3.5' />
              </Button>
            </div>
          ))}
        </div>
      )}
      {error && <p className='text-destructive text-xs'>{error}</p>}
    </div>
  )
}

/** meta JSON 对象输入（session_config / pacing；保存前 JSON.parse + 必须对象） */
function JsonTextarea({
  id,
  label,
  hint,
  value,
  error,
  onChange,
}: {
  id: string
  label: string
  hint: string
  value: string
  error?: string
  onChange: (text: string) => void
}) {
  return (
    <div className='space-y-1.5'>
      <Label htmlFor={id}>{label}</Label>
      <Textarea
        id={id}
        rows={4}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={hint}
        className='font-mono text-xs'
        aria-invalid={Boolean(error)}
      />
      {error ? (
        <p className='text-destructive text-xs'>{error}</p>
      ) : (
        <p className='text-muted-foreground text-xs'>JSON 对象，保存前校验格式；留空则不写入该键。</p>
      )}
    </div>
  )
}

/** 贴样例 JSON → 一键生成模板（纯前端推断，结果回填到输入框由用户复核） */
function SampleJsonImport({
  kind,
  onApply,
}: {
  kind: 'request' | 'response'
  onApply: (text: string) => string
}) {
  const [text, setText] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = () => {
    setError(null)
    setMessage(null)
    try {
      setMessage(onApply(text) || '已生成，请核对后再保存')
    } catch (err) {
      setError(err instanceof Error ? err.message : '解析失败')
    }
  }

  return (
    <div className='border-border/60 space-y-1.5 rounded-lg border border-dashed p-2.5'>
      <p className='text-xs font-medium'>
        {kind === 'request'
          ? '粘贴样例请求 JSON → 一键生成请求模板'
          : '粘贴样例响应 JSON → 一键生成响应解析'}
      </p>
      <Textarea
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={
          kind === 'request'
            ? '{\n  "type": "input_audio_buffer.append",\n  "audio": "<base64...>"\n}'
            : '{\n  "type": "response.audio_transcript.delta",\n  "transcript": "..."\n}'
        }
        className='font-mono text-xs'
        aria-label={kind === 'request' ? '样例请求 JSON' : '样例响应 JSON'}
      />
      <div className='flex flex-wrap items-center gap-2'>
        <Button type='button' size='sm' variant='outline' className='h-7 text-xs' onClick={run}>
          一键解析
        </Button>
        {message && <span className='text-muted-foreground text-xs'>{message}</span>}
        {error && <span className='text-destructive text-xs'>{error}</span>}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* A3（INT-1791）：gRPC 消息字段预览 + 响应解析预览面板               */
/* ------------------------------------------------------------------ */

/** gRPC 请求 / 响应消息字段预览（符号表来自上传端点；无符号表时整块不渲染） */
function ProtoFieldList({ title, fields }: { title: string; fields: ApiProtoField[] }) {
  return (
    <div className='space-y-1'>
      <Label className='text-xs'>{title}</Label>
      {fields.length === 0 ? (
        <p className='text-muted-foreground border-border/60 rounded-md border border-dashed p-2 text-center text-xs'>
          无字段
        </p>
      ) : (
        <div className='border-border/60 max-h-32 overflow-y-auto rounded-md border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='h-7 text-xs'>字段</TableHead>
                <TableHead className='h-7 text-xs'>类型</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {fields.map((field) => (
                <TableRow key={field.path}>
                  <TableCell className='font-mono text-xs'>{field.path}</TableCell>
                  <TableCell className='text-xs'>
                    {field.type}
                    {field.repeated ? '（repeated）' : ''}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

/**
 * 各协议的样例文案（§二.4）：HTTP 贴整个响应体（含标准信封）、WS 贴单事件 payload、
 * SSE 贴单个事件的 data、gRPC 贴 `MessageToDict` 结果。后端 `parse-preview` 是协议无关的
 * 纯函数，「归一后的 dict」这一口径由各协议的执行适配器保证。
 */
const PARSE_SAMPLE_HINTS: Record<
  ApiProtocol,
  { placeholder: string; hint: string }
> = {
  http: {
    placeholder:
      '{\n  "code": 0,\n  "data": { "asr_result": "你好", "is_sentence_end": true }\n}',
    hint: 'HTTP：贴完整响应体；标准信封 {"code":0,"data":{…}} 会先解包再按路径取值。',
  },
  websocket: {
    placeholder: '{\n  "asr_result": "你好",\n  "is_sentence_end": true\n}',
    hint: 'WebSocket：贴单个事件的 payload（归一后的事件体）。',
  },
  sse: {
    placeholder: '{\n  "asr_result": "你好",\n  "is_sentence_end": true\n}',
    hint: 'SSE：贴单个事件的 data（逐帧 JSON，非整段流）。',
  },
  grpc: {
    placeholder: '{\n  "asrResult": "你好",\n  "isSentenceEnd": true\n}',
    hint: 'gRPC：贴 MessageToDict 结果（字段名为 proto 原始名，repeated 为数组）。',
  },
}

/**
 * 响应解析预览面板（A3 §二.4；`POST /apis/parse-preview`，INT-1772 纯函数端点）。
 * 用**当前草稿**里的解析器 / 映射直接试算，不发保存；样例按协议给不同文案与错误提示。
 */
function ParsePreviewPanel({
  protocol,
  draft,
}: {
  protocol: ApiProtocol
  draft: ResponseParserDraft
}) {
  const [sample, setSample] = useState('')
  const [result, setResult] = useState<ApiParsePreviewResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const sampleHint = PARSE_SAMPLE_HINTS[protocol]

  const handleRun = async () => {
    setError(null)
    setResult(null)
    if (!sample.trim()) {
      setError('请先贴一段样例响应')
      return
    }
    // result_parser 先按保存同口径校验（非法 JSON / 非对象 → 不请求）
    let parser: Record<string, unknown> | undefined
    if (draft.resultParser.trim()) {
      let parsed: unknown
      try {
        parsed = JSON.parse(draft.resultParser)
      } catch {
        setError('响应解析器（result_parser）不是合法 JSON 对象，先修正再测试')
        return
      }
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setError('响应解析器（result_parser）必须是 JSON 对象')
        return
      }
      parser = parsed as Record<string, unknown>
    }
    // 能解析成 JSON 就发结构化对象；厂商原始文本按字符串原样交给后端（不报错）
    let sampleResponse: unknown = sample
    try {
      sampleResponse = JSON.parse(sample)
    } catch {
      sampleResponse = sample
    }
    setRunning(true)
    try {
      setResult(
        await parseApiResponsePreview({
          sampleResponse,
          resultParser: parser,
        })
      )
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : '解析预览失败')
    } finally {
      setRunning(false)
    }
  }

  const extractedEntries = Object.entries(result?.extracted ?? {})

  return (
    <div className='border-border/60 space-y-2 rounded-lg border p-3'>
      <div className='flex flex-wrap items-start justify-between gap-2'>
        <div>
          <Label htmlFor='parse-preview-sample'>测试解析（样例响应预览）</Label>
          <p className='text-muted-foreground text-xs'>
            用当前填写的解析器 / 映射试算，不保存、不请求厂商接口。{sampleHint.hint}
          </p>
        </div>
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='h-7 flex-none text-xs'
          disabled={running}
          onClick={handleRun}
        >
          {running ? '解析中…' : '测试解析'}
        </Button>
      </div>
      <Textarea
        id='parse-preview-sample'
        rows={5}
        value={sample}
        onChange={(e) => setSample(e.target.value)}
        placeholder={sampleHint.placeholder}
        className='font-mono text-xs'
        aria-label='样例响应'
      />
      {error && <p className='text-destructive text-xs'>{error}</p>}
      {result && (
        <div className='space-y-1.5'>
          {extractedEntries.length === 0 ? (
            <p className='text-muted-foreground text-xs'>
              没有字段被提取到（检查路径或样例结构）。
            </p>
          ) : (
            <div className='border-border/60 overflow-x-auto rounded-md border'>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className='h-7 text-xs'>解析字段</TableHead>
                    <TableHead className='h-7 text-xs'>提取值</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {extractedEntries.map(([key, value]) => (
                    <TableRow key={key}>
                      <TableCell className='font-mono text-xs'>{key}</TableCell>
                      <TableCell className='font-mono text-xs'>
                        {typeof value === 'string' ? value : JSON.stringify(value)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {result.unresolved.length > 0 && (
            <p className='text-xs text-amber-600 dark:text-amber-400'>
              路径未命中：{result.unresolved.join('、')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
