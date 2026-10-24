/**
 * 新增/编辑 API 弹窗（INT-1777，母卡 INT-1750 C5 规格 v3；interfaces/features/test-execution/modals）。
 *
 * 五页签骨架：
 * - 基础：现有字段（名称 / 关联算法 / 最大并发 / 设备类型 / 描述 / 端点列表与密钥池）口径不变，
 *   新增 audio_config 编辑区（顶层列 apis.audio_config，四项：采样率/位深/通道数/容器）；
 * - 请求模板：写 meta（按目标设备类型显隐 HTTP / WS 两组键）；
 * - 响应解析 / 输出字段 / 映射：本卡只落页签骨架 + 占位空态，内容由实施卡二填。
 *
 * meta 读写口径（母卡 §3.1，后端整块 replace）：打开弹窗以 GET /apis 的 api.meta 为 base；
 * 页签只覆盖自己声明的键；保存提交合并后的整对象；清空的键从 base 删除；**未触碰任何 meta 字段不发 meta**。
 * audio_config 未改动不发该键，显式「清除」传 {}；禁止写 meta.audio_config。
 * 页签显隐用 deriveApiTargetDeviceType（编辑态显式 deviceType 优先，新增态按端点草稿派生）。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { FileText, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import type { ApiConfig } from '@/domain/models/apiConfig'
import { cn } from '@/lib/utils'

import {
  AUDIO_BIT_DEPTH_OPTIONS,
  AUDIO_CHANNEL_OPTIONS,
  AUDIO_CONTAINER_OPTIONS,
  AUDIO_SAMPLE_RATE_OPTIONS,
  HTTP_METHOD_OPTIONS,
  audioConfigDraftFrom,
  buildAudioConfig,
  deriveDraftTargetDeviceType,
  emptyAudioConfigDraft,
  emptyRequestTemplateDraft,
  mergeRequestTemplateMeta,
  newKeyValueRow,
  requestTemplateDraftFromMeta,
  type AudioConfigDraft,
  type BodyTemplateMode,
  type KeyValueRow,
  type MetaDraftError,
  type RequestTemplateDraft,
} from './api-edit-dialog-model'

const apiFormSchema = z.object({
  name: z.string().min(1, '请输入必填项'),
  algorithmType: z.string().min(1, '请输入必填项'),
  maxProcess: z.number().int().min(1).max(128),
  description: z.string().optional(),
  // INT-1433：设备类型可选（http_api/websocket_api）或 auto 按端点协议派生（缺省 http_api）
  deviceType: z.enum(['auto', 'http_api', 'websocket_api']),
})

type ApiForm = z.infer<typeof apiFormSchema>

type ApiTab = 'basic' | 'request' | 'response' | 'output' | 'mapping'

const API_TABS: ReadonlyArray<{ value: ApiTab; label: string; placeholder: string }> = [
  { value: 'basic', label: '基础', placeholder: '' },
  { value: 'request', label: '请求模板', placeholder: '' },
  { value: 'response', label: '响应解析', placeholder: '响应解析器与各输出映射（result_parser / asr_mapping 等 meta 键）' },
  { value: 'output', label: '输出字段', placeholder: '该算法类型声明的输出字段（只读，算法类型级）' },
  { value: 'mapping', label: '映射', placeholder: '该算法类型的 API 输出映射（只读，算法类型级）' },
]

/** base-ui Select 不接受空串为「未设置」，统一用哨兵值映射草稿里的 '' */
const UNSET = '__unset__'

// base-ui Select 关闭态用 items 显示 label（否则直接回显 value；INT-1633 同口径）
const UNSET_OPTION = { value: UNSET, label: '未设置' }
const DEVICE_TYPE_OPTIONS = [
  { value: 'auto', label: '自动（按端点协议派生）' },
  { value: 'http_api', label: 'HTTP API' },
  { value: 'websocket_api', label: 'Realtime WS' },
] as const
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
  // 请求模板页签草稿（meta 键级合并；未触碰不发 meta）
  const [metaDraft, setMetaDraft] = useState<RequestTemplateDraft>(emptyRequestTemplateDraft)
  const [metaTouched, setMetaTouched] = useState(false)
  const [metaErrors, setMetaErrors] = useState<MetaDraftError[]>([])
  // audio_config 草稿（顶层列；未改动不发该键）
  const [audioDraft, setAudioDraft] = useState<AudioConfigDraft>(emptyAudioConfigDraft)
  const [audioTouched, setAudioTouched] = useState(false)
  const [audioCleared, setAudioCleared] = useState(false)
  // INT-1433：设备类型派生提示（auto 态展示实际将路由到的类型）
  const firstEndpoint = endpoints.find((e) => e.endpoint.trim())?.endpoint.trim() ?? ''

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
    values: {
      name: api?.name ?? '',
      algorithmType:
        api?.algorithmType ??
        algorithmList.find((a) => a.id === globalAlgorithmId)?.name ??
        '',
      maxProcess: api?.defaultMaxProcess ?? 5,
      description: api?.description ?? '',
      deviceType:
        api?.deviceType === 'http_api' || api?.deviceType === 'websocket_api'
          ? api.deviceType
          : 'auto',
    },
  })

  const watchedDeviceType = form.watch('deviceType')
  const algorithmType = form.watch('algorithmType')

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

  // 每次打开重置页签与草稿（关闭再打开不残留上次输入）
  useEffect(() => {
    if (!open) return
    setTab('basic')
    setMetaDraft(requestTemplateDraftFromMeta(api?.meta))
    setMetaTouched(false)
    setMetaErrors([])
    setAudioDraft(audioConfigDraftFrom(api?.audioConfig))
    setAudioTouched(false)
    setAudioCleared(false)
  }, [open, api])

  // 最新快照到达后刷新草稿（用户已触碰的字段不覆盖）
  useEffect(() => {
    if (!open || !detailQuery.data) return
    const fresh = detailQuery.data
    if (!metaTouched) setMetaDraft(requestTemplateDraftFromMeta(fresh.meta))
    if (!audioTouched) {
      setAudioDraft(audioConfigDraftFrom(fresh.audioConfig))
      setAudioCleared(false)
    }
  }, [open, detailQuery.data, metaTouched, audioTouched])

  // 页签显隐依据：显式 deviceType 优先，auto 按当前端点草稿派生（编辑态与新增态同口径）
  const targetDeviceType = deriveDraftTargetDeviceType(watchedDeviceType, endpoints)
  const isWebSocket = targetDeviceType === 'websocket_api'

  const metaErrorOf = (field: MetaDraftError['field']) =>
    metaErrors.find((error) => error.field === field)?.message

  const updateMeta = (patch: Partial<RequestTemplateDraft>) => {
    setMetaDraft((prev) => ({ ...prev, ...patch }))
    setMetaTouched(true)
    setMetaErrors([])
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

  const updateEndpoint = (key: string, patch: Partial<EndpointFormRow>) => {
    setEndpoints((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const addEndpoint = () => {
    setEndpoints((prev) => [...prev, { ...ENDPOINT_EMPTY, key: endpointKey() }])
  }

  const removeEndpoint = (key: string) => {
    setEndpoints((prev) => prev.filter((row) => row.key !== key))
  }

  const handleSave = async (values: ApiForm) => {
    const payload: Partial<ApiConfig> & { name: string } = {
      id: api?.id,
      name: values.name,
      algorithmType: values.algorithmType,
      defaultMaxProcess: values.maxProcess,
      description: values.description || null,
      // INT-1433：auto = 不落显式 deviceType（建任务时按端点协议派生）
      deviceType: values.deviceType === 'auto' ? null : values.deviceType,
      endpoints: endpoints
        .filter((row) => row.endpoint.trim())
        .map((row) => ({
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

    // 请求模板（meta）：未触碰 → 不下发 meta 键；触碰 → 提交 base 合并后的整对象
    if (metaTouched) {
      const { meta, errors } = mergeRequestTemplateMeta(baseApi?.meta, metaDraft, targetDeviceType)
      if (errors.length > 0) {
        setMetaErrors(errors)
        setTab('request')
        return
      }
      payload.meta = meta
    }
    // audio_config（顶层列）：未改动 → 不下发；显式清除 → {}
    if (audioTouched) {
      payload.audioConfig = audioCleared ? {} : buildAudioConfig(baseApi?.audioConfig, audioDraft)
    }

    await save(payload)
    onOpenChange(false)
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

        <form onSubmit={form.handleSubmit(handleSave)} className='flex min-h-0 flex-col gap-3'>
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
                    onValueChange={(value) => form.setValue('algorithmType', value ?? '')}
                  >
                    <SelectTrigger className={cn('w-full justify-between', !form.watch('algorithmType') && 'text-muted-foreground')}>
                      <SelectValue placeholder='请选择算法' />
                    </SelectTrigger>
                    <SelectContent>
                      {algorithmList.map((algorithm) => (
                        <SelectItem key={algorithm.id} value={algorithm.name}>
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
                    {...form.register('maxProcess', { valueAsNumber: true })}
                  />
                </div>

                {/* 设备类型（INT-1433：可选 http_api/websocket_api，或 auto 按端点协议派生，缺省 http_api；
                    Realtime WS（websocket_api）是建任务路由到 Realtime 执行器的前置） */}
                <div className='space-y-1.5'>
                  <Label>设备类型</Label>
                  <Select
                    value={form.watch('deviceType')}
                    items={DEVICE_TYPE_OPTIONS}
                    onValueChange={(value) =>
                      form.setValue('deviceType', (value ?? 'auto') as ApiForm['deviceType'])
                    }
                  >
                    <SelectTrigger className='w-full justify-between'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='auto'>自动（按端点协议派生）</SelectItem>
                      <SelectItem value='http_api'>HTTP API</SelectItem>
                      <SelectItem value='websocket_api'>Realtime WS</SelectItem>
                    </SelectContent>
                  </Select>
                  {form.watch('deviceType') === 'auto' && (
                    <p className='text-muted-foreground text-xs'>
                      {firstEndpoint
                        ? `将按端点协议派生为：${
                            /^wss?:\/\//i.test(firstEndpoint) ? 'Realtime WS' : 'HTTP API'
                          }`
                        : '未配置端点时缺省为 HTTP API'}
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
                          <div className='grid grid-cols-5 gap-1.5'>
                            <Input
                              value={row.name}
                              onChange={(e) => updateEndpoint(row.key, { name: e.target.value })}
                              placeholder='名称'
                              className='h-7 text-xs'
                            />
                            <Input
                              value={row.priority}
                              type='number'
                              min={1}
                              max={10}
                              onChange={(e) => updateEndpoint(row.key, { priority: e.target.value })}
                              placeholder='优先级'
                              className='h-7 text-xs'
                            />
                            <Input
                              value={row.maxProcess}
                              type='number'
                              min={1}
                              max={100}
                              onChange={(e) => updateEndpoint(row.key, { maxProcess: e.target.value })}
                              placeholder='最大进程'
                              className='h-7 text-xs'
                            />
                            <Input
                              value={row.maxTimeout}
                              type='number'
                              min={1}
                              max={300}
                              onChange={(e) => updateEndpoint(row.key, { maxTimeout: e.target.value })}
                              placeholder='超时(s)'
                              className='h-7 text-xs'
                            />
                            <Input
                              value={row.maxAudioDuration}
                              type='number'
                              min={1}
                              onChange={(e) => updateEndpoint(row.key, { maxAudioDuration: e.target.value })}
                              placeholder='音频时长(s)'
                              className='h-7 text-xs'
                            />
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

              {/* 请求模板页签：写 meta，按目标设备类型显隐（旧键保留不删，只隐藏） */}
              <TabsContent value='request' className='space-y-3'>
                <div className='bg-muted/40 text-muted-foreground rounded-lg border p-2.5 text-xs'>
                  按目标设备类型显隐，当前：
                  <Badge variant='secondary' className='mx-1'>
                    {isWebSocket ? 'Realtime WS（websocket_api）' : 'HTTP API（http_api）'}
                  </Badge>
                  切换设备类型 / 端点协议后旧键保留不删，只隐藏；切回即恢复。
                </div>

                {isWebSocket ? (
                  <>
                    <KeyValueEditor
                      label='WS 请求头'
                      addLabel='添加请求头'
                      emptyHint='未配置 WS 请求头'
                      rows={metaDraft.wsHeaders}
                      error={metaErrorOf('wsHeaders')}
                      onChange={(rows) => updateMeta({ wsHeaders: rows })}
                    />
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

              {/* 以下三个页签本卡只落骨架 + 占位空态，内容由实施卡二填 */}
              {API_TABS.filter((item) => item.placeholder).map((item) => (
                <TabsContent key={item.value} value={item.value}>
                  <TabPlaceholder
                    title={item.label}
                    placeholder={item.placeholder}
                    hasAlgorithm={Boolean(algorithmType)}
                  />
                </TabsContent>
              ))}
            </div>
          </Tabs>

          <DialogFooter>
            <Button variant='outline' type='button' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type='submit'>{form.formState.isSubmitting ? '保存中…' : '保存'}</Button>
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

/** 未实施页签占位空态（响应解析 / 输出字段 / 映射，内容由实施卡二填） */
function TabPlaceholder({
  title,
  placeholder,
  hasAlgorithm,
}: {
  title: string
  placeholder: string
  hasAlgorithm: boolean
}) {
  return (
    <Empty className='border-border/60 min-h-[18rem] border'>
      <EmptyHeader>
        <EmptyMedia variant='icon'>
          <FileText aria-hidden='true' className='size-4' />
        </EmptyMedia>
        <EmptyTitle>{hasAlgorithm ? `${title}页签建设中` : '未选择关联算法'}</EmptyTitle>
        <EmptyDescription>
          {hasAlgorithm
            ? `${placeholder}，将在后续版本提供。`
            : '请先在「基础」页签选择关联算法，再回来查看该页签。'}
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
