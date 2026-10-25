/**
 * 新增/编辑 API 弹窗（INT-1777 五页签骨架 + INT-1778 后三个页签；母卡 INT-1750 C5 规格 v3；
 * interfaces/features/test-execution/modals）。
 *
 * 五个页签：
 * - 基础：现有字段（名称 / 关联算法 / 最大并发 / 协议 + 流式性 / 描述 / 端点列表与密钥池），
 *   新增 audio_config 编辑区（顶层列 apis.audio_config，四项：采样率/位深/通道数/容器）；
 * - 请求模板：写 meta（协议决定请求/响应配置区，流式性决定轮次/会话配置区）；
 * - 响应解析：写 meta（result_parser 等 8 个解析器键；顶部固定提示 C0 裁定口径）；
 * - 输出字段 / 映射：只读，算法类型作用域（数据源见 application/test-execution/useApiAlgorithmReadonly）。
 *
 * 协议 × 流式性（INT-1800 / B0）：两维独立可组合，下拉 4 值、未上线协议置灰并提示；
 * 流式开关按 B0 §3.2.3 可用矩阵锁定（当前只有 http+非流式、websocket+流式可写）。
 * 保存只提交 protocol / streaming，永不提交 `device_type`（后端写侧显式 400）。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ExternalLink, FileText, Plus, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import {
  useAlgorithmApiMappings,
  useAlgorithmApiParams,
  type ReadonlyQueryState,
} from '@/application/test-execution/useApiAlgorithmReadonly'
import { useApisCrud } from '@/application/test-execution/useApisCrud'
import { useTestAlgorithmOptions } from '@/application/test-execution/useTestAlgorithmOptions'
import { fetchApi } from '@/infrastructure/api/test-execution-api'
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
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
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
import type { ApiConfig } from '@/domain/models/apiConfig'
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
} from '@/domain/models/apiProtocol'
import { cn } from '@/lib/utils'

import {
  AUDIO_BIT_DEPTH_OPTIONS,
  AUDIO_CHANNEL_OPTIONS,
  AUDIO_CONTAINER_OPTIONS,
  AUDIO_SAMPLE_RATE_OPTIONS,
  ENDPOINT_NUMERIC_RULES,
  HTTP_METHOD_OPTIONS,
  RESPONSE_PARSER_PATH_DEFAULTS,
  audioConfigDraftFrom,
  buildAudioConfig,
  emptyAudioConfigDraft,
  emptyRequestTemplateDraft,
  emptyResponseParserDraft,
  mergeRequestTemplateMeta,
  mergeResponseParserMeta,
  newKeyValueRow,
  requestTemplateDraftFromMeta,
  responseParserDraftFromMeta,
  validateEndpointNumbers,
  type AppendModeValue,
  type AudioConfigDraft,
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

type ApiTab = 'basic' | 'request' | 'response' | 'output' | 'mapping'

const API_TABS: ReadonlyArray<{ value: ApiTab; label: string }> = [
  { value: 'basic', label: '基础' },
  { value: 'request', label: '请求模板' },
  { value: 'response', label: '响应解析' },
  { value: 'output', label: '输出字段' },
  { value: 'mapping', label: '映射' },
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
  // audio_config 草稿（顶层列；未改动不发该键）
  const [audioDraft, setAudioDraft] = useState<AudioConfigDraft>(emptyAudioConfigDraft)
  const [audioTouched, setAudioTouched] = useState(false)
  const [audioCleared, setAudioCleared] = useState(false)

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

  // INT-1778 只读页签数据源（algorithm:read）：切到相关页签才请求，避免每次打开多发两个 GET。
  // 响应解析页签也要 params 数据——C0 兜底口径的判定依据就是同一次
  // GET /algorithm/params?param_type=api 有没有 direction=output 行。
  const paramsQuery = useAlgorithmApiParams(
    algorithmType,
    open && (tab === 'response' || tab === 'output')
  )
  const mappingsQuery = useAlgorithmApiMappings(algorithmType, open && tab === 'mapping')

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

  // C0（INT-1745）判定结果展示：只说「该算法类型的声明情况」，不描述系统当前行为
  const c0Status = !algorithmType
    ? '未选择关联算法，无法判定'
    : paramsQuery.state === 'loading'
      ? '正在读取该算法类型的输出字段声明…'
      : paramsQuery.state === 'ready'
        ? paramsQuery.noOutputDeclared
          ? '该类型未声明输出字段 → 解析走本页 meta 兜底'
          : `该类型已声明 ${paramsQuery.outputParams.length} 个输出字段 → 本页解析器不兜底`
        : paramsQuery.state === 'forbidden'
          ? '无权查看算法配置，无法判定'
          : paramsQuery.state === 'error'
            ? '算法配置读取失败，无法判定'
            : '未判定'

  const metaErrorOf = (field: MetaDraftError['field']) =>
    metaErrors.find((error) => error.field === field)?.message

  const updateMeta = (patch: Partial<RequestTemplateDraft>) => {
    setMetaDraft((prev) => ({ ...prev, ...patch }))
    setMetaTouched(true)
    setMetaErrors([])
  }

  const responseErrorOf = (field: ResponseParserDraftError['field']) =>
    responseErrors.find((error) => error.field === field)?.message

  const updateResponse = (patch: Partial<ResponseParserDraft>) => {
    setResponseDraft((prev) => ({ ...prev, ...patch }))
    setResponseTouched(true)
    setResponseErrors([])
  }

  const updateAudio = (patch: Partial<AudioConfigDraft>) => {
    setAudioDraft((prev) => ({ ...prev, ...patch }))
    setAudioTouched(true)
    setAudioCleared(false)
  }

  const clearAudioConfig = () => {
    setAudioDraft(emptyAudioConfigDraft())
    setAudioTouched(true)
    setAudioCleared(true)
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
    if (metaTouched || responseTouched) {
      let meta: Record<string, unknown> = baseApi?.meta ?? {}
      const requestResult = metaTouched
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

    // INT-1939：只有保存成功才关闭弹窗；失败时 toast 已由 useApisCrud 给出，
    // 弹窗与五个页签草稿原样保留，保存钮恢复可点，可在弹窗内直接重试。
    if (await save(payload)) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{api ? '编辑 API' : '新增 API'}</DialogTitle>
          <DialogDescription>
            {api ? '修改被测 API 配置，保存后列表自动刷新' : '新增被测 API，保存后列表自动刷新'}
          </DialogDescription>
        </DialogHeader>

        {/* INT-1939：校验统一走 zod（中文内联提示），关掉浏览器原生校验气泡 */}
        <form
          onSubmit={form.handleSubmit(handleSave)}
          noValidate
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
                  <Label htmlFor='max-process'>最大并发</Label>
                  <Input
                    id='max-process'
                    type='number'
                    min={1}
                    max={128}
                    aria-invalid={Boolean(form.formState.errors.maxProcess)}
                    {...form.register('maxProcess', { valueAsNumber: true })}
                  />
                  {form.formState.errors.maxProcess && (
                    <p className='text-destructive text-xs'>
                      {form.formState.errors.maxProcess.message}
                    </p>
                  )}
                </div>

                {/* 协议 × 流式性（INT-1800 / B0 §3.2）：两个独立维度，不互相推断。
                    协议下拉 4 值，sse / grpc 未上线 → 置灰并提示；流式开关按可用矩阵锁定。 */}
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
                    协议只存规范值（http / websocket / sse / grpc）；sse 与 gRPC 的执行实现尚未上线，
                    对应选项置灰。
                  </p>
                </div>

                <div className='space-y-1.5'>
                  <div className='flex items-center justify-between gap-2'>
                    <Label htmlFor='api-streaming'>流式</Label>
                    <div className='flex items-center gap-2'>
                      <span className='text-muted-foreground text-xs'>
                        {streamingLabel(watchedStreaming)}
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
                      当前协议只放行一种流式性（{watchedProtocol === 'websocket' ? '流式' : '非流式'}），
                      开关暂锁定；两种形态都可用后开放。
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

                {/* INT-1777 audio_config（顶层列 apis.audio_config，不是 meta.audio_config） */}
                <div className='border-border/60 space-y-2 rounded-lg border p-3'>
                  <div className='flex flex-wrap items-start justify-between gap-2'>
                    <div>
                      <Label>音频格式（audio_config）</Label>
                      <p className='text-muted-foreground text-xs'>
                        目标音频格式声明；未配置时运行时回退 24000Hz / s16 / 单声道 / pcm。
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
                  <div className='grid grid-cols-2 gap-2'>
                    <div className='space-y-1'>
                      <Label className='text-xs'>采样率</Label>
                      <Select
                        value={audioDraft.sampleRate || UNSET}
                        items={SAMPLE_RATE_OPTIONS}
                        onValueChange={(value) =>
                          updateAudio({ sampleRate: value && value !== UNSET ? value : '' })
                        }
                      >
                        <SelectTrigger className='w-full justify-between'>
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
                        value={audioDraft.bitDepth || UNSET}
                        items={BIT_DEPTH_OPTIONS}
                        onValueChange={(value) =>
                          updateAudio({ bitDepth: value && value !== UNSET ? value : '' })
                        }
                      >
                        <SelectTrigger className='w-full justify-between'>
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
                        value={audioDraft.channels || UNSET}
                        items={CHANNEL_OPTIONS}
                        onValueChange={(value) =>
                          updateAudio({ channels: value && value !== UNSET ? value : '' })
                        }
                      >
                        <SelectTrigger className='w-full justify-between'>
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
                        value={audioDraft.container || UNSET}
                        items={CONTAINER_OPTIONS}
                        onValueChange={(value) =>
                          updateAudio({ container: value && value !== UNSET ? value : '' })
                        }
                      >
                        <SelectTrigger className='w-full justify-between'>
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
                  <p className='text-muted-foreground text-xs'>
                    {audioCleared
                      ? '保存后将清空 audio_config（提交 {}）。'
                      : '未改动时不提交 audio_config；清空某一项则从 audio_config 删除该键。'}
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
                      暂无端点，点击「添加端点」配置（优先级/最大进程/超时/音频时长）
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
                          <div className='grid grid-cols-5 items-start gap-1.5'>
                            <Input
                              value={row.name}
                              onChange={(e) => updateEndpoint(row.key, { name: e.target.value })}
                              placeholder='名称'
                              className='h-7 text-xs'
                            />
                            {/* INT-1939 返工：四项整数改由 validateEndpointNumbers 自查并给中文内联提示
                                （表单 noValidate 后原生 min/max 只是展示，不再拦截提交） */}
                            {ENDPOINT_NUMERIC_RULES.map((rule) => (
                              <div key={rule.field} className='space-y-0.5'>
                                <Input
                                  value={row[rule.field]}
                                  type='number'
                                  min={rule.min}
                                  max={rule.max ?? undefined}
                                  aria-label={`端点${rule.label}`}
                                  aria-invalid={Boolean(endpointErrorOf(row.key, rule.field))}
                                  onChange={(e) =>
                                    setEndpointNumber(row.key, rule.field, e.target.value)
                                  }
                                  placeholder={rule.label}
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

                {isWebSocket ? (
                  <KeyValueEditor
                    label='WS 请求头'
                    addLabel='添加请求头'
                    emptyHint='未配置 WS 请求头'
                    rows={metaDraft.wsHeaders}
                    error={metaErrorOf('wsHeaders')}
                    onChange={(rows) => updateMeta({ wsHeaders: rows })}
                  />
                ) : (
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

                {/* 轮次 / 会话配置区：只由流式性决定（B0 §3.5；非流式无会话概念） */}
                {watchedStreaming && (
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

                <Separator />
                <div className='space-y-1.5'>
                  <Label htmlFor='meta-vendor-adapter'>厂商适配器（vendor_adapter）</Label>
                  <Input
                    id='meta-vendor-adapter'
                    value={metaDraft.vendorAdapter}
                    onChange={(e) => updateMeta({ vendorAdapter: e.target.value })}
                    placeholder='留空 = 使用默认适配器'
                  />
                  <p className='text-muted-foreground text-xs'>
                    只填部署已注册的适配器名；留空使用默认适配器。写错值会在执行期被拒绝，该 API 的任务将无法运行。
                  </p>
                </div>
              </TabsContent>

              {/* 响应解析页签（INT-1778 §2.3）：写 meta 的 8 个解析器键 */}
              <TabsContent value='response' className='space-y-3'>
                <div className='bg-muted/40 space-y-1.5 rounded-lg border p-2.5 text-xs'>
                  <p className='flex flex-wrap items-center gap-1.5 font-medium'>
                    解析兜底口径（C0 裁定口径 · INT-1745）
                    <Badge variant='secondary' className='font-normal'>
                      {c0Status}
                    </Badge>
                  </p>
                  <p className='text-muted-foreground'>
                    按 C0 裁定口径：本页 meta 解析器只在该算法类型
                    <span className='text-foreground font-medium'>零输出字段声明</span>
                    时逐键兜底 —— 判定方式是同一次{' '}
                    <code className='font-mono'>
                      GET /algorithm/params?algorithm_type=…&amp;param_type=api
                    </code>{' '}
                    没有 <code className='font-mono'>direction=output</code> 行；该类型声明了输出字段时，
                    解析以「输出字段」页签的声明为准，本页解析器不作兜底，两者不按字段混用。
                  </p>
                </div>

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

                <div className='grid grid-cols-2 gap-2'>
                  <ResponsePathInput
                    id='meta-asr-mapping'
                    label='ASR 文本映射（asr_mapping）'
                    defaultValue={RESPONSE_PARSER_PATH_DEFAULTS.asrMapping}
                    value={responseDraft.asrMapping}
                    onChange={(value) => updateResponse({ asrMapping: value })}
                  />
                  <ResponsePathInput
                    id='meta-trans-mapping'
                    label='翻译文本映射（trans_mapping）'
                    defaultValue={RESPONSE_PARSER_PATH_DEFAULTS.transMapping}
                    value={responseDraft.transMapping}
                    onChange={(value) => updateResponse({ transMapping: value })}
                  />
                  <ResponsePathInput
                    id='meta-sentence-end-mapping'
                    label='句结束标志（sentence_end_mapping）'
                    defaultValue={RESPONSE_PARSER_PATH_DEFAULTS.sentenceEndMapping}
                    value={responseDraft.sentenceEndMapping}
                    onChange={(value) => updateResponse({ sentenceEndMapping: value })}
                  />
                  <ResponsePathInput
                    id='meta-session-end-mapping'
                    label='会话结束标志（session_end_mapping）'
                    defaultValue={RESPONSE_PARSER_PATH_DEFAULTS.sessionEndMapping}
                    value={responseDraft.sessionEndMapping}
                    onChange={(value) => updateResponse({ sessionEndMapping: value })}
                  />
                  <ResponsePathInput
                    id='meta-error-code-mapping'
                    label='业务错误码（error_code_mapping）'
                    defaultValue={RESPONSE_PARSER_PATH_DEFAULTS.errorCodeMapping}
                    value={responseDraft.errorCodeMapping}
                    onChange={(value) => updateResponse({ errorCodeMapping: value })}
                  />
                  <ResponsePathInput
                    id='meta-error-msg-mapping'
                    label='业务错误信息（error_msg_mapping）'
                    defaultValue={RESPONSE_PARSER_PATH_DEFAULTS.errorMsgMapping}
                    value={responseDraft.errorMsgMapping}
                    onChange={(value) => updateResponse({ errorMsgMapping: value })}
                  />
                </div>

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
              </TabsContent>

              {/* 输出字段页签（INT-1778 §2.4）：只读，算法类型级 */}
              <TabsContent value='output' className='space-y-3'>
                {algorithmType ? (
                  <>
                    <AlgorithmTypeBanner
                      onClose={() => onOpenChange(false)}
                      showJump={paramsQuery.state !== 'forbidden'}
                    />
                    <ReadonlyTabBody
                      state={paramsQuery.state}
                      isEmpty={paramsQuery.outputParams.length === 0}
                      loadingHint='正在读取该算法类型的输出字段声明…'
                      errorHint='输出字段读取失败'
                      emptyTitle='该算法类型未声明输出字段'
                      emptyDescription='该算法类型未声明输出字段，解析走 meta 兜底（见响应解析页签）。'
                    >
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>参数代码</TableHead>
                            <TableHead>类型</TableHead>
                            <TableHead>响应路径（field_path）</TableHead>
                            <TableHead>标签</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {paramsQuery.outputParams.map((param) => (
                            <TableRow key={param.id}>
                              <TableCell className='font-mono text-xs'>{param.paramCode}</TableCell>
                              <TableCell className='text-xs'>{param.paramType}</TableCell>
                              <TableCell className='font-mono text-xs'>
                                {param.fieldPath ?? '—'}
                              </TableCell>
                              <TableCell className='text-xs'>{param.label ?? '—'}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </ReadonlyTabBody>
                  </>
                ) : (
                  <ReadonlyTabUnselected tabLabel='输出字段' />
                )}
              </TabsContent>

              {/* 映射页签（INT-1778 §2.5）：只读，唯一数据源 /algorithm/mappings?source_type=api */}
              <TabsContent value='mapping' className='space-y-3'>
                {algorithmType ? (
                  <>
                    <AlgorithmTypeBanner
                      onClose={() => onOpenChange(false)}
                      showJump={mappingsQuery.state !== 'forbidden'}
                    />
                    <ReadonlyTabBody
                      state={mappingsQuery.state}
                      isEmpty={mappingsQuery.rows.length === 0}
                      loadingHint='正在读取该算法类型的 API 输出映射…'
                      errorHint='映射读取失败'
                      emptyTitle='该算法类型未配置来源为 API 输出的映射'
                      emptyDescription='该算法类型没有 source=api 的参数映射；如需新增，请到算法配置页的评估参数映射里添加。'
                    >
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>源参数（source_param）</TableHead>
                            <TableHead>目标维度</TableHead>
                            <TableHead>目标参数（target_param）</TableHead>
                            <TableHead>转换（transform_type）</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {mappingsQuery.rows.map((mapping) => (
                            <TableRow key={mapping.id}>
                              <TableCell className='font-mono text-xs'>
                                {mapping.sourceParam}
                              </TableCell>
                              <TableCell className='text-xs'>
                                {mapping.dimensionName ??
                                  (mapping.dimensionId != null
                                    ? `#${mapping.dimensionId}`
                                    : '—')}
                              </TableCell>
                              <TableCell className='font-mono text-xs'>
                                {mapping.targetParam || '—'}
                              </TableCell>
                              <TableCell className='text-xs'>
                                {mapping.transformType || '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </ReadonlyTabBody>
                  </>
                ) : (
                  <ReadonlyTabUnselected tabLabel='映射' />
                )}
              </TabsContent>
            </div>
          </Tabs>

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
  )
}

/** 键值表编辑器（headers / ws_headers；空行忽略，键名必填且不重复） */
function KeyValueEditor({
  label,
  addLabel,
  emptyHint,
  rows,
  error,
  onChange,
}: {
  label: string
  addLabel: string
  emptyHint: string
  rows: KeyValueRow[]
  error?: string
  onChange: (rows: KeyValueRow[]) => void
}) {
  const patchRow = (id: string, patch: Partial<KeyValueRow>) =>
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)))
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

/** 响应解析页签的单条路径输入（6 个 *_mapping 键；占位符 = 后端内置缺省，不预填不写库） */
function ResponsePathInput({
  id,
  label,
  defaultValue,
  value,
  onChange,
}: {
  id: string
  label: string
  defaultValue: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className='space-y-1'>
      <Label htmlFor={id} className='text-xs'>
        {label}
      </Label>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={`留空 = 默认 ${defaultValue}`}
        className='font-mono text-xs'
      />
    </div>
  )
}

/** 算法类型级横幅（输出字段 / 映射页签共用；母卡 §2.4 / §2.5） */
function AlgorithmTypeBanner({
  onClose,
  showJump,
}: {
  onClose: () => void
  showJump: boolean
}) {
  return (
    <div className='bg-muted/40 flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2.5 text-xs'>
      <p className='text-muted-foreground flex-1'>
        <Badge variant='secondary' className='mr-1.5'>
          算法类型级
        </Badge>
        算法类型级声明，本类型下所有 API 共用；
        {showJump ? '此处只读，维护入口在算法配置页。' : '当前账号不可查看。'}
      </p>
      {showJump && <AlgorithmConfigJump onBeforeNavigate={onClose} />}
    </div>
  )
}

/**
 * 「去算法配置」跳转按钮。
 * useNavigate 需要路由上下文，所以只有真的渲染这个按钮时才调用（未选算法 / 无权限时不渲染）。
 */
function AlgorithmConfigJump({ onBeforeNavigate }: { onBeforeNavigate: () => void }) {
  const navigate = useNavigate()
  return (
    <Button
      type='button'
      variant='outline'
      size='sm'
      className='h-7 flex-none gap-1 text-xs'
      onClick={() => {
        onBeforeNavigate()
        void navigate({ to: '/AlgorithmConfig' })
      }}
    >
      <ExternalLink aria-hidden='true' className='size-3.5' />
      去算法配置
    </Button>
  )
}

/** 只读页签的取数状态包装：加载 / 无权（403 降级）/ 错误 / 空态都收敛在这里 */
function ReadonlyTabBody({
  state,
  isEmpty,
  loadingHint,
  errorHint,
  emptyTitle,
  emptyDescription,
  children,
}: {
  state: ReadonlyQueryState
  isEmpty: boolean
  loadingHint: string
  errorHint: string
  emptyTitle: string
  emptyDescription: string
  children: ReactNode
}) {
  if (state === 'forbidden') {
    return (
      <ReadonlyTabEmpty
        title='无权查看算法配置'
        description='当前账号缺少 algorithm:read 权限，本页签不可用；不影响其它页签保存。'
      />
    )
  }
  if (state === 'error') {
    return <ReadonlyTabEmpty title={errorHint} description='算法配置暂时读取不到，稍后可重新打开弹窗再试。' />
  }
  if (state !== 'ready') {
    return (
      <div className='text-muted-foreground flex items-center justify-center gap-2 py-10 text-xs'>
        <Spinner className='size-4' />
        {loadingHint}
      </div>
    )
  }
  if (isEmpty) {
    return <ReadonlyTabEmpty title={emptyTitle} description={emptyDescription} />
  }
  return <div className='border-border/60 overflow-x-auto rounded-lg border'>{children}</div>
}

function ReadonlyTabEmpty({ title, description }: { title: string; description: string }) {
  return (
    <Empty className='border-border/60 border'>
      <EmptyHeader>
        <EmptyMedia variant='icon'>
          <FileText aria-hidden='true' className='size-4' />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}

/** 未选关联算法时的只读页签空态 */
function ReadonlyTabUnselected({ tabLabel }: { tabLabel: string }) {
  return (
    <ReadonlyTabEmpty
      title='未选择关联算法'
      description={`请先在「基础」页签选择关联算法，再回来查看「${tabLabel}」页签（数据按算法类型汇总，与单个 API 无关）。`}
    />
  )
}
