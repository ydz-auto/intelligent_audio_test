/**
 * 设备新增/编辑抽屉（16_设备域.md §6.2；Sheet sideDrawer `sm:max-w-[600px]`）。
 * 分节「基本信息」（名称/描述）+ 分节随页签分叉：
 * - 测试设备：型号/设备类型/设备系统/系统版本/API级别（随系统切换）/应用名称/应用版本/连接方式/
 *   设备序列号/IP·端口(conditional remote)/驱动关键字（V9.7.10 keywords select）/是否需要提示词/算法类型/状态采集（只读）/
 *   高级设置（备注/标签/自定义属性/优先级）
 * - 播放设备：型号/设备类型/系统唯一标识/通道索引/支持的通道数/支持的格式/采样率/声压映射
 * - 测试 API：API名称/供应商/API端点/关联算法（默认全局算法）/协议/环境/最大进程数/超时/音频时长/
 *   端点列表（ArrayField，编辑回显）
 * 表单按 AGENTS §3.7 落 RHF+zod（schema 见 lib/device-form-schema.ts）。
 * P2-1 返修：编辑提交 patch 只携带表单可编辑字段，不重置 status/occupied/labId/labName/
 * driverName/lastOnlineAt/createdAt 等非表单字段。
 */
import { ChevronDown, Plus, ScanLine, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type { DevicesTabKey } from '@/features/devices/constants'
import type { DeviceMutateState } from '@/features/devices/types'
import {
  apiDeviceFormSchema,
  playbackDeviceFormSchema,
  testDeviceFormSchema,
} from '@/features/devices/lib/device-form-schema'
import { normalizeDeviceSystem } from '@/features/devices/lib/device-system'
import { useDeviceMutations, useDriverKeywords } from '@/application/devices/use-devices'
import { useSplMappingsByDevice } from '@/application/spl/useSplMappings'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import { useGlobalAlgorithm } from '@/application/hooks/use-global-algorithm'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type { ApiEndpoint } from '@/domain/models/apiDevice'

export interface DeviceMutateDrawerProps {
  state: DeviceMutateState
  onOpenChange: (open: boolean) => void
  /** 扫描预填（§6.1：随页签分叉） */
  prefill?: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> | null
  /** INT-1029 扫描入口：测试/播放信息分节「扫描设备」钮 → 打开扫描弹窗 */
  onScan?: () => void
  /** INT-1029 抽屉内扫描「选择」→ 回填当前表单（编辑/新增态均可用；nonce 递增触发） */
  scanFill?: {
    nonce: number
    kind: DevicesTabKey
    prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice>
  } | null
}

const SYSTEM_OPTIONS = [
  { value: 'iOS', label: 'iOS' },
  { value: 'Android', label: 'Android' },
  { value: 'HarmonyOS', label: 'HarmonyOS' },
]

const ANDROID_API_LEVELS = ['26', '28', '30', '32', '33', '34']
const HARMONY_API_LEVELS = ['3.0', '3.1', '3.2', '4.0', '4.2']
const FORMAT_OPTIONS = ['WAV', 'MP3', 'FLAC', 'AAC', 'OGG', 'WMA']
const PROTOCOL_OPTIONS = ['http', 'https', 'ws', 'wss']
const ENV_OPTIONS = [
  { value: 'development', label: '开发' },
  { value: 'testing', label: '测试' },
  { value: 'production', label: '生产' },
]
/** 代理类型选项（api_test_service PROXY_TYPES 契约 http/https/socks5/socks5h；空=不使用代理） */
const PROXY_TYPE_OPTIONS = [
  { value: '', label: '不使用代理' },
  { value: 'http', label: 'HTTP' },
  { value: 'https', label: 'HTTPS' },
  { value: 'socks5', label: 'SOCKS5' },
  { value: 'socks5h', label: 'SOCKS5H' },
]

/** API 端点编辑行（§6.2 apiEndpoint ArrayField；INT-355 §5.3 口径子集） */
interface EndpointFormRow {
  key: string
  endpoint: string
  name: string
  priority: string
  maxProcess: string
  maxTimeout: string
  maxAudioDuration: string
}

const ENDPOINT_EMPTY: EndpointFormRow = {
  key: '',
  endpoint: '',
  name: '',
  priority: '1',
  maxProcess: '1',
  maxTimeout: '30',
  maxAudioDuration: '60',
}

function endpointKey(): string {
  return Math.random().toString(36).slice(2, 9)
}

/**
 * INT-1029 扫描结果回填当前表单（对齐 V9.7.10 useDeviceSelection.selectDevice 口径）：
 * - 名称编辑态保留用户已填值（V9.7.10 `(!isEditMode || !formValues.name)` 语义），为空时取扫描值；
 * - 硬件字段（型号/序列号/系统/系统版本/应用名/应用版本/IP）一律以扫描值为准。
 */
export function mergeScanPrefill(
  form: ReturnType<typeof useForm<DeviceForm>>,
  kind: DevicesTabKey,
  prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice>
): void {
  if (kind === 'test') {
    const p = prefill as Partial<TestDevice>
    const current = form.getValues() as Extract<DeviceForm, { kind: 'test' }>
    form.reset({
      ...current,
      name: (current.name ?? '').trim() ? current.name : (p.name ?? current.name),
      model: p.model ?? current.model,
      system: p.system ? (normalizeDeviceSystem(p.system)?.label ?? current.system) : current.system,
      systemVersion: p.systemVersion ?? current.systemVersion,
      appName: p.appName ?? current.appName,
      appVersion: p.appVersion ?? current.appVersion,
      serialNumber: p.serialNumber ?? current.serialNumber,
      ip: p.ip ?? current.ip,
    })
  } else if (kind === 'playback') {
    const p = prefill as Partial<PlaybackDevice>
    const current = form.getValues() as Extract<DeviceForm, { kind: 'playback' }>
    form.reset({
      ...current,
      name: (current.name ?? '').trim() ? current.name : (p.name ?? current.name),
      model: p.model ?? current.model,
      deviceUniqueId: p.deviceUniqueId ?? current.deviceUniqueId,
      channelIndex: p.channelIndex != null ? String(p.channelIndex) : current.channelIndex,
      sampleRate: p.sampleRate != null ? String(p.sampleRate) : current.sampleRate,
      deviceType: p.deviceType ?? current.deviceType,
    })
  }
}

/** 三页签表单 schema（§6.2 分叉；z.discriminatedUnion 单 useForm 承载）。
 * 用 extend 而非展开 shape：保留各页签 schema 的 superRefine（如 API 代理跨字段校验）。 */
const deviceFormSchema = z.discriminatedUnion('kind', [
  testDeviceFormSchema.extend({ kind: z.literal('test') }),
  playbackDeviceFormSchema.extend({ kind: z.literal('playback') }),
  apiDeviceFormSchema.extend({ kind: z.literal('api') }),
])

type DeviceForm = z.infer<typeof deviceFormSchema>

function buildDefaults(
  state: DeviceMutateState,
  prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> | null | undefined,
  globalAlgorithmId: string
): DeviceForm {
  if (state.kind === 'test') {
    const device = state.mode === 'edit' ? (state.device as TestDevice | null) : null
    const scanPrefill = prefill as Partial<TestDevice> | null
    return {
      kind: 'test',
      name: device?.name ?? scanPrefill?.name ?? '',
      description: device?.description ?? '',
      remark: device?.remark ?? '',
      model: device?.model ?? scanPrefill?.model ?? '',
      deviceType: device?.type ?? scanPrefill?.type ?? 'physical',
      system: normalizeDeviceSystem(device?.system ?? scanPrefill?.system)?.label ?? 'Android',
      systemVersion: device?.systemVersion ?? scanPrefill?.systemVersion ?? '',
      apiLevel: device?.apiLevel ?? '',
      connectionType: device?.connectionType ?? 'usb',
      serialNumber: device?.serialNumber ?? scanPrefill?.serialNumber ?? '',
      keywords: device?.keywords ?? scanPrefill?.keywords ?? '',
      ip: device?.ip ?? scanPrefill?.ip ?? '',
      appName: device?.appName ?? scanPrefill?.appName ?? '',
      appVersion: device?.appVersion ?? scanPrefill?.appVersion ?? '',
      port: '5555',
      needsPromptAudio: device?.needsPromptAudio ?? false,
      algorithms: device?.supportedAlgorithms ?? [],
      tags: device?.tags ?? [],
      customAttributes: (device?.customAttributes ?? []).join(', '),
      priority: String(device?.priority ?? 5),
    }
  }
  if (state.kind === 'playback') {
    const device = state.mode === 'edit' ? (state.device as PlaybackDevice | null) : null
    return {
      kind: 'playback',
      name: device?.name ?? '',
      description: device?.description ?? '',
      model: device?.model ?? '',
      deviceType: device?.deviceType ?? 'dry',
      deviceUniqueId: device?.deviceUniqueId ?? '',
      channelIndex: String(device?.channelIndex ?? 0),
      supportedChannels: device?.supportedChannels != null ? String(device.supportedChannels) : '',
      supportedFormats: device?.supportedFormats ?? [],
      sampleRate: String(device?.sampleRate ?? 48000),
      splMappingId: device?.currentSplMappingId != null ? String(device.currentSplMappingId) : '',
    }
  }
  const device = state.mode === 'edit' ? (state.device as ApiDevice | null) : null
  return {
    kind: 'api',
    name: device?.name ?? '',
    description: device?.description ?? '',
    vendor: device?.vendor ?? '',
    apiUrl: device?.apiUrl ?? '',
    protocol: device?.protocol ?? 'https',
    environment: device?.environment ?? 'testing',
    proxyType: device?.proxyType ?? '',
    proxyUrl: device?.proxyUrl ?? '',
    algorithmType: device?.algorithmType ?? globalAlgorithmId ?? '',
    maxProcess: String(device?.defaultMaxProcess ?? 5),
    maxTimeout: String(device?.defaultMaxTimeout ?? 30),
    maxAudioDuration: String(device?.defaultMaxAudioDuration ?? 60),
  }
}

function Field({
  label,
  required,
  error,
  children,
  className,
}: {
  label: string
  required?: boolean
  error?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <Label className='text-xs'>
        {label}
        {required && <span className='text-destructive'> *</span>}
      </Label>
      {children}
      {error && <p className='text-destructive text-xs'>{error}</p>}
    </div>
  )
}

/**
 * 标签/算法多选 chips（§6.2 BadgeListCell 输入态）。
 * option 支持纯字符串或 {value,label}——算法选项显示中文名（label）、提交类型码（value）。
 */
function ChipField({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string
  options: readonly (string | { value: string; label: string })[]
  selected: string[]
  onToggle: (value: string) => void
}) {
  return (
    <div className='flex flex-col gap-1'>
      <Label className='text-xs'>{label}</Label>
      <div className='flex flex-wrap gap-1.5'>
        {options.map((option) => {
          const value = typeof option === 'string' ? option : option.value
          const display = typeof option === 'string' ? option : option.label
          return (
            <button
              key={value}
              type='button'
              onClick={() => onToggle(value)}
              className={cn(
                'rounded-md border px-2 py-1 text-xs transition-colors',
                selected.includes(value)
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'hover:bg-muted'
              )}
            >
              {display}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function DeviceMutateDrawer(props: DeviceMutateDrawerProps) {
  const { state, prefill, onScan, scanFill } = props
  const open = state.open
  const kind = state.kind
  const isEdit = state.mode === 'edit' && state.device != null
  const editingDevice = isEdit ? state.device : null
  const { createTest, updateTest, createPlayback, updatePlayback, createApi, updateApi } =
    useDeviceMutations()
  const driverKeywordsQuery = useDriverKeywords()
  // 声压映射选项仅编辑态（设备已存在）加载该设备映射（V9.7.10 loadSplMappings 同源 GET /spl/by-device/{id}）；
  // 新增态 deviceId 为空 → 无选项（设备创建后再经行操作关联）
  const editingPlaybackId = kind === 'playback' && isEdit ? (state.device?.id ?? null) : null
  const splMappingsQuery = useSplMappingsByDevice(editingPlaybackId)
  const driverKeywords = driverKeywordsQuery.data ?? []
  const splOptions = splMappingsQuery.data ?? []
  // 算法类型选项（INT-1213：真实 GET /algorithm/options，显示中文名；V9.7.10 algorithmSelect 口径）
  // INT-1239：改壳层门控版（['shell','algorithm','options']，enabled: algorithm:read）——device_admin
  // 无 algorithm:read 不下发请求（后端 RBAC 403）；选项为 {value,name}，抽屉统一映射 {value,label}。
  const {
    options: algorithmRawOptions,
    isLoading: algorithmOptionsLoading,
    canRead: canReadAlgorithm,
  } = useAlgorithmOptions()
  const algorithmOptions = useMemo(
    () => algorithmRawOptions.map((o) => ({ value: o.value, label: o.name })),
    [algorithmRawOptions]
  )
  // 关联算法新增态默认全局算法（16_设备域.md §6.2「默认全局算法」）
  const { algorithmId: globalAlgorithmId } = useGlobalAlgorithm()

  const form = useForm<DeviceForm>({
    resolver: zodResolver(deviceFormSchema),
    values: buildDefaults(state, prefill, globalAlgorithmId),
  })

  // INT-1029 抽屉内扫描「选择」→ 回填当前表单（编辑/新增态均可用；nonce 递增触发）
  useEffect(() => {
    if (scanFill && state.open && scanFill.kind === kind) {
      mergeScanPrefill(form, scanFill.kind, scanFill.prefill)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanFill?.nonce])

  // API 端点数组（§6.2 apiEndpoint ArrayField；受控于本地 state，编辑回显）
  const [endpoints, setEndpoints] = useState<EndpointFormRow[]>([])
  const [saving, setSaving] = useState(false)

  // 打开 API 编辑时回显端点列表；关闭/切换页签时清空
  useEffect(() => {
    if (kind === 'api' && state.open && state.mode === 'edit' && state.device) {
      const api = state.device as ApiDevice
      setEndpoints(
        (api.endpoints ?? []).map((ep) => ({
          key: endpointKey(),
          endpoint: ep.endpoint,
          name: ep.name ?? '',
          priority: String(ep.priority ?? 1),
          maxProcess: String(ep.maxProcess ?? 1),
          maxTimeout: String(ep.maxTimeout ?? 30),
          maxAudioDuration: String(ep.maxAudioDuration ?? 60),
        }))
      )
    } else if (!state.open) {
      setEndpoints([])
    }
  }, [kind, state.open, state.mode, state.device])

  const handleOpenChange = (next: boolean) => {
    props.onOpenChange(next)
  }

  const toggleChip = (field: 'algorithms' | 'supportedFormats' | 'tags') => (value: string) => {
    const current = (form.getValues(field) ?? []) as string[]
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value]
    form.setValue(field, next)
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

  const handleSave = async (values: DeviceForm) => {
    setSaving(true)
    try {
      if (values.kind === 'test') {
        const editable = {
          name: values.name.trim(),
          description: values.description?.trim() || null,
          remark: values.remark?.trim() || null,
          keywords: values.keywords?.trim() || null,
          model: values.model.trim(),
          type: values.deviceType,
          system: values.system,
          systemVersion: values.systemVersion.trim(),
          apiLevel: values.apiLevel?.trim() || null,
          appName: values.appName.trim(),
          appVersion: values.appVersion.trim(),
          connectionType: values.connectionType,
          serialNumber: values.serialNumber.trim(),
          ip: values.connectionType === 'remote' ? (values.ip?.trim() || null) : null,
          needsPromptAudio: values.needsPromptAudio,
          supportedAlgorithms: values.algorithms.length > 0 ? values.algorithms : null,
          tags: values.tags.length > 0 ? values.tags : null,
          priority: Number(values.priority) || 5,
          // 高级设置「自定义属性」（§6.2；逗号分隔 key=value，接线后按后端契约）
          customAttributes: values.customAttributes?.trim()
            ? values.customAttributes
                .split(/[,，]/)
                .map((item) => item.trim())
                .filter(Boolean)
            : null,
        }
        if (isEdit) {
          // P2-1：patch 只携带表单可编辑字段，不重置 status/occupied/labId/labName/driverName/lastOnlineAt/location/keywords
          await updateTest.mutateAsync({ id: editingDevice!.id, patch: editable })
        } else {
          await createTest.mutateAsync({
            ...editable,
            status: 'offline',
            occupied: false,
            labId: null,
            labName: null,
            driverName: null,
            maxAudioDuration: null,
            location: null,
            lastOnlineAt: null,
          })
        }
      } else if (values.kind === 'playback') {
        const splMappingId = values.splMappingId ? Number(values.splMappingId) : null
        const editable = {
          name: values.name.trim(),
          description: values.description?.trim() || null,
          model: values.model.trim(),
          deviceType: values.deviceType as PlaybackDevice['deviceType'],
          deviceUniqueId: values.deviceUniqueId.trim(),
          channelIndex: Number(values.channelIndex) || 0,
          supportedChannels: values.supportedChannels ? Number(values.supportedChannels) || null : null,
          supportedFormats: values.supportedFormats.length > 0 ? values.supportedFormats : null,
          sampleRate: Number(values.sampleRate) || 48000,
          currentSplMappingId: splMappingId,
          currentSplMappingName: splOptions.find((m) => m.id === splMappingId)?.name ?? null,
        }
        if (isEdit) {
          await updatePlayback.mutateAsync({ id: editingDevice!.id, patch: editable })
        } else {
          await createPlayback.mutateAsync({
            ...editable,
            status: 'offline',
            occupied: false,
            labId: null,
            labName: null,
          })
        }
      } else {
        const editable = {
          name: values.name.trim(),
          description: values.description?.trim() || null,
          vendor: values.vendor?.trim() || null,
          apiUrl: values.apiUrl.trim(),
          protocol: values.protocol,
          environment: values.environment || null,
          meta: { protocol: values.protocol, environment: values.environment },
          // INT-1029：每 API 代理配置（契约格式 user:pass@host:port；空串归一 null）
          proxyType: values.proxyType?.trim() || null,
          proxyUrl: values.proxyUrl?.trim() || null,
          algorithmType: values.algorithmType,
          defaultMaxProcess: Number(values.maxProcess) || 5,
          defaultMaxTimeout: Number(values.maxTimeout) || 30,
          defaultMaxAudioDuration: Number(values.maxAudioDuration) || 60,
          endpoints: endpoints
            .filter((row) => row.endpoint.trim())
            .map(
              (row): ApiEndpoint => ({
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
              })
            ),
        }
        if (isEdit) {
          await updateApi.mutateAsync({ id: editingDevice!.id, patch: editable })
        } else {
          await createApi.mutateAsync({
            ...editable,
            status: 'offline',
            healthScore: null,
            rmsSplMappingId: null,
            rmsSplMappingName: null,
            occupied: false,
          })
        }
      }
      toast.success(
        kind === 'test' ? '测试设备已保存' : kind === 'playback' ? '播放设备已保存' : '测试 API 已保存'
      )
      handleOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const title = isEdit ? '编辑设备' : DEVICE_ADD_TITLE[kind]
  // RHF 判别联合 errors 字段访问宽松化（按 kind 分支读取对应字段）
  const fieldErrors = form.formState.errors as Record<string, { message?: string } | undefined>
  const errors = fieldErrors

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent className='sm:max-w-[600px]'>
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            登记或修改{kind === 'test' ? '测试设备' : kind === 'playback' ? '播放设备' : '测试 API'}信息。
          </SheetDescription>
        </SheetHeader>

        <form onSubmit={form.handleSubmit(handleSave)} className='flex min-h-0 flex-1 flex-col'>
          <div className='flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-2'>
            {/* 基本信息 */}
            <section className='flex flex-col gap-2'>
              <h3 className='text-sm font-medium'>基本信息</h3>
              <Field label='名称' required error={errors.name?.message}>
                <Input
                  {...form.register('name')}
                  aria-invalid={Boolean(errors.name)}
                  placeholder='如：音箱-客厅位'
                  className='h-8'
                />
              </Field>
              <Field label='描述'>
                <Input
                  {...form.register('description')}
                  placeholder='设备用途或工位说明'
                  className='h-8'
                />
              </Field>
            </section>

            {kind === 'test' && (
              <section className='flex flex-col gap-2'>
                <div className='flex items-center justify-between'>
                  <h3 className='text-sm font-medium'>测试设备信息</h3>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='h-7 gap-1 text-xs'
                    onClick={onScan}
                  >
                    <ScanLine aria-hidden='true' className='size-3.5' />
                    扫描设备
                  </Button>
                </div>
                <div className='grid grid-cols-2 gap-2.5'>
                  <Field label='型号' required error={errors.model?.message}>
                    <Input {...form.register('model')} placeholder='如：旗舰 S1' className='h-8' />
                  </Field>
                  <Field label='设备类型' required error={errors.deviceType?.message}>
                    <Select
                      value={form.watch('deviceType')}
                      onValueChange={(value) => form.setValue('deviceType', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='physical'>真机</SelectItem>
                        <SelectItem value='http_api'>HTTP API</SelectItem>
                        <SelectItem value='websocket_api'>Realtime WS</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='设备系统' required error={errors.system?.message}>
                    <Select
                      value={form.watch('system')}
                      onValueChange={(value) => form.setValue('system', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SYSTEM_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='系统版本' required error={errors.systemVersion?.message}>
                    <Input {...form.register('systemVersion')} placeholder='如：12' className='h-8' />
                  </Field>
                  {/* API 级别（随设备系统切换，§6.2/设备管理:262-278） */}
                  {form.watch('system') === 'iOS' ? (
                    <Field label='iOS 版本'>
                      <Input {...form.register('systemVersion')} disabled className='h-8' />
                    </Field>
                  ) : (
                    <Field
                      label={form.watch('system') === 'HarmonyOS' ? 'HarmonyOS API级别' : 'Android API级别'}
                    >
                      <Select
                        value={form.watch('apiLevel')}
                        onValueChange={(value) => form.setValue('apiLevel', value ?? '')}
                      >
                        <SelectTrigger size='sm' className='w-full'>
                          <SelectValue placeholder='选择 API 级别' />
                        </SelectTrigger>
                        <SelectContent>
                          {(form.watch('system') === 'HarmonyOS'
                            ? HARMONY_API_LEVELS
                            : ANDROID_API_LEVELS
                          ).map((level) => (
                            <SelectItem key={level} value={level}>
                              API {level}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                  )}
                  <Field label='应用名称' required error={errors.appName?.message}>
                    <Input {...form.register('appName')} className='h-8' />
                  </Field>
                  <Field label='应用版本' required error={errors.appVersion?.message}>
                    <Input {...form.register('appVersion')} className='h-8' />
                  </Field>
                  <Field label='连接方式' required error={errors.connectionType?.message}>
                    <Select
                      value={form.watch('connectionType')}
                      onValueChange={(value) => form.setValue('connectionType', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='usb'>USB连接</SelectItem>
                        <SelectItem value='remote'>远程连接</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='设备序列号' required error={errors.serialNumber?.message}>
                    <Input {...form.register('serialNumber')} placeholder='连接后自动填充' className='h-8' />
                  </Field>
                  {form.watch('connectionType') === 'remote' && (
                    <>
                      <Field label='IP 地址'>
                        <Input {...form.register('ip')} placeholder='192.168.x.x' className='h-8' />
                      </Field>
                      <Field label='端口'>
                        <Input {...form.register('port')} type='number' className='h-8' />
                      </Field>
                    </>
                  )}
                  {/* 驱动关键字（V9.7.10 添加测试设备 keywords 选填；GET /test-devices/driver-keywords 真实选项，INT-721 接线） */}
                  <Field label='驱动关键字' className='col-span-2'>
                    <Select
                      value={form.watch('keywords') ?? ''}
                      onValueChange={(value) => form.setValue('keywords', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue placeholder='请选择驱动匹配关键字' />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value=''>不使用驱动关键字</SelectItem>
                        {driverKeywords.map((kw) => (
                          <SelectItem key={kw.keywords} value={kw.keywords}>
                            {kw.name}（{kw.system}）
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                </div>
                <label className='flex items-center gap-2 text-sm'>
                  <Switch
                    size='sm'
                    checked={form.watch('needsPromptAudio')}
                    onCheckedChange={(checked) => form.setValue('needsPromptAudio', checked)}
                  />
                  是否需要提示词
                </label>
                <ChipField
                  label='算法类型'
                  options={canReadAlgorithm ? algorithmOptions : []}
                  selected={form.watch('algorithms')}
                  onToggle={toggleChip('algorithms')}
                />
                {!canReadAlgorithm && (
                  <p className='text-muted-foreground text-xs'>无算法读取权限，暂不可配置算法类型</p>
                )}
                {/* 状态采集字段（§6.2：只读展示设备实时采集值） */}
                <div className='border-border/60 grid grid-cols-3 gap-2 rounded-lg border p-2.5 text-xs'>
                  <div className='flex flex-col gap-0.5'>
                    <span className='text-muted-foreground'>电池状态</span>
                    <span>87% · 正常</span>
                  </div>
                  <div className='flex flex-col gap-0.5'>
                    <span className='text-muted-foreground'>存储状态</span>
                    <span>剩余 42GB</span>
                  </div>
                  <div className='flex flex-col gap-0.5'>
                    <span className='text-muted-foreground'>网络状态</span>
                    <span>Wi-Fi 已连接</span>
                  </div>
                </div>
                {/* 高级设置（§6.2 Collapsible：备注/标签/自定义属性/优先级） */}
                <Collapsible>
                  <CollapsibleTrigger
                    render={
                      <Button variant='ghost' size='sm' className='h-7 gap-1 px-1 text-xs' />
                    }
                  >
                    <ChevronDown aria-hidden='true' className='size-3.5' />
                    高级设置
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className='grid grid-cols-2 gap-2.5 pt-2'>
                      <Field label='备注'>
                        <Input {...form.register('remark')} placeholder='与基本信息「描述」独立' className='h-8' />
                      </Field>
                      <Field label='优先级'>
                        <Select
                          value={form.watch('priority')}
                          onValueChange={(value) => form.setValue('priority', value ?? '5')}
                        >
                          <SelectTrigger size='sm' className='w-full'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Array.from({ length: 10 }, (_, i) => String(i + 1)).map((value) => (
                              <SelectItem key={value} value={value}>
                                {value}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                    </div>
                    <div className='flex flex-col gap-2 pt-2'>
                      <ChipField
                        label='标签'
                        options={['远场', '近场', '车载', '会议室', '手机', '音柱']}
                        selected={form.watch('tags')}
                        onToggle={toggleChip('tags')}
                      />
                      <Field label='自定义属性'>
                        <Input
                          {...form.register('customAttributes')}
                          placeholder='如：房间=客厅, 朝向=南（逗号分隔）'
                          className='h-8'
                        />
                      </Field>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </section>
            )}

            {kind === 'playback' && (
              <section className='flex flex-col gap-2'>
                <div className='flex items-center justify-between'>
                  <h3 className='text-sm font-medium'>播放设备信息</h3>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='h-7 gap-1 text-xs'
                    onClick={onScan}
                  >
                    <ScanLine aria-hidden='true' className='size-3.5' />
                    扫描设备
                  </Button>
                </div>
                <div className='grid grid-cols-2 gap-2.5'>
                  <Field label='型号' required error={errors.model?.message}>
                    <Input {...form.register('model')} className='h-8' />
                  </Field>
                  <Field label='设备类型' required error={errors.deviceType?.message}>
                    <Select
                      value={form.watch('deviceType')}
                      onValueChange={(value) => form.setValue('deviceType', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='dry'>干声设备</SelectItem>
                        <SelectItem value='noise'>噪声设备</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='系统唯一标识' required error={errors.deviceUniqueId?.message}>
                    <Input {...form.register('deviceUniqueId')} placeholder='连接后自动填充' className='h-8' />
                  </Field>
                  <Field label='通道索引'>
                    <Input {...form.register('channelIndex')} type='number' className='h-8' />
                  </Field>
                  <Field label='支持的通道数'>
                    <Input {...form.register('supportedChannels')} type='number' placeholder='如：2' className='h-8' />
                  </Field>
                  <Field label='采样率' required error={errors.sampleRate?.message}>
                    <Input {...form.register('sampleRate')} type='number' className='h-8' />
                  </Field>
                  <Field label='声压映射'>
                    <Select
                      value={form.watch('splMappingId')}
                      onValueChange={(value) => form.setValue('splMappingId', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue placeholder='不使用声压映射' />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value=''>不使用声压映射</SelectItem>
                        {splOptions.map((mapping) => (
                          <SelectItem key={mapping.id} value={String(mapping.id)}>
                            {mapping.name}（{mapping.calibrationStatus === 'calibrated' ? '已校准' : '未校准'}）
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                </div>
                <ChipField
                  label='支持的格式'
                  options={FORMAT_OPTIONS}
                  selected={form.watch('supportedFormats')}
                  onToggle={toggleChip('supportedFormats')}
                />
              </section>
            )}

            {kind === 'api' && (
              <section className='flex flex-col gap-2'>
                <h3 className='text-sm font-medium'>API 信息</h3>
                <div className='grid grid-cols-2 gap-2.5'>
                  <Field label='供应商'>
                    <Input {...form.register('vendor')} className='h-8' />
                  </Field>
                  <Field label='协议' required error={errors.protocol?.message}>
                    <Select
                      value={form.watch('protocol')}
                      onValueChange={(value) => form.setValue('protocol', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PROTOCOL_OPTIONS.map((value) => (
                          <SelectItem key={value} value={value}>
                            {value.toUpperCase()}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='环境'>
                    <Select
                      value={form.watch('environment')}
                      onValueChange={(value) => form.setValue('environment', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ENV_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  {/* 代理配置（INT-1029：每 API 可配代理；proxy_url 契约格式 user:pass@host:port 不含 scheme） */}
                  <Field label='代理类型'>
                    <Select
                      value={form.watch('proxyType') ?? ''}
                      onValueChange={(value) => form.setValue('proxyType', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue placeholder='不使用代理'>
                          {PROXY_TYPE_OPTIONS.find((o) => o.value === form.watch('proxyType'))
                            ?.label ?? '不使用代理'}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {PROXY_TYPE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='代理地址' error={errors.proxyUrl?.message}>
                    <Input
                      {...form.register('proxyUrl')}
                      placeholder='user:pass@host:port'
                      aria-invalid={Boolean(errors.proxyUrl)}
                      className='h-8'
                    />
                  </Field>
                  <Field label='关联算法' required error={errors.algorithmType?.message}>
                    <Select
                      value={form.watch('algorithmType')}
                      onValueChange={(value) => form.setValue('algorithmType', value ?? '')}
                      disabled={!canReadAlgorithm}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue
                          placeholder={
                            !canReadAlgorithm
                              ? '无权限'
                              : algorithmOptionsLoading
                                ? '加载中…'
                                : '请选择算法'
                          }
                        >
                          {canReadAlgorithm &&
                            (algorithmOptions.find((o) => o.value === form.watch('algorithmType'))?.label ?? '')}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {canReadAlgorithm &&
                          algorithmOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='默认最大进程数'>
                    <Input {...form.register('maxProcess')} type='number' className='h-8' />
                  </Field>
                  <Field label='默认最大超时（秒）'>
                    <Input {...form.register('maxTimeout')} type='number' className='h-8' />
                  </Field>
                  <Field label='默认最大音频时长（秒）'>
                    <Input {...form.register('maxAudioDuration')} type='number' className='h-8' />
                  </Field>
                </div>
                <p className='text-muted-foreground text-xs'>
                  代理地址格式：user:pass@host:port（不含 http:// 前缀）；选择代理类型后必填。
                </p>
                <Field label='API 端点' required error={errors.apiUrl?.message}>
                  <Input {...form.register('apiUrl')} placeholder='https://api.example.com/v1/asr' className='h-8' />
                </Field>
                {/* 端点列表（§6.2 apiEndpoint ArrayField：URL / 名称 / 优先级 / 最大进程 / 超时 / 音频时长） */}
                <div className='flex flex-col gap-2'>
                  <div className='flex items-center justify-between'>
                    <Label className='text-xs'>端点列表</Label>
                    <Button type='button' variant='outline' size='sm' className='h-7 gap-1 text-xs' onClick={addEndpoint}>
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
                              placeholder='/v1/asr/stream'
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
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            )}
          </div>

          <SheetFooter>
            <Button type='button' variant='outline' onClick={() => handleOpenChange(false)}>
              取消
            </Button>
            <Button type='submit' disabled={saving}>
              {saving ? '保存中...' : '保存'}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}

const DEVICE_ADD_TITLE: Record<DevicesTabKey, string> = {
  test: '添加测试设备',
  playback: '添加播放设备',
  api: '添加测试API',
}
