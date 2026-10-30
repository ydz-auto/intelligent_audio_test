/**
 * 设备新增/编辑抽屉（16_设备域.md §6.2；Sheet sideDrawer `sm:max-w-[600px]`）。
 * 分节「基本信息」（名称/描述）+ 分节随页签分叉：
 * - 测试设备：型号/设备类型/设备系统/系统版本/API级别（随系统切换）/应用名称/应用版本/连接方式/
 *   设备序列号/IP(conditional remote)/驱动关键字（V9.7.10 keywords select）/是否需要提示词/算法类型/
 *   高级设置（备注/标签/自定义属性/优先级）
 * - 播放设备：型号/设备类型/系统唯一标识/通道索引/支持的通道数/支持的格式/采样率/声压映射
 *
 * INT-2153：**测试 API 不再走本抽屉**。新增与编辑统一开 §5.3 API 编辑弹窗
 * （`features/test-execution/modals/api-edit-dialog`，基础/请求模板/响应解析/参数配置四页签），
 * 否则创建时看不到 meta 配置、且同一资源存在两套字段不一致的表单。
 * 表单按 AGENTS §3.7 落 RHF+zod（schema 见 lib/device-form-schema.ts）。
 * P2-1 返修：编辑提交 patch 只携带表单可编辑字段，不重置 status/occupied/labId/labName/
 * driverName/lastOnlineAt/createdAt 等非表单字段。
 */
import { ChevronDown, ScanLine } from 'lucide-react'
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
  playbackDeviceFormSchema,
  testDeviceFormSchema,
} from '@/features/devices/lib/device-form-schema'
import { normalizeDeviceSystem } from '@/features/devices/lib/device-system'
import { useDeviceMutations, useDriverKeywords } from '@/application/devices/use-devices'
import { useSplMappingsByDevice } from '@/application/spl/useSplMappings'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'

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

/**
 * base-ui Select 闭合态标签解析只认 Root 的 `items`（未传时直接回显原始 value，
 * 见 node_modules/@base-ui/react/internals/resolveValueLabel.js resolveSelectedLabel）：
 * 程序设值/编辑回填的 Select 必须补 items，否则显示 physical / usb / offline_duration 等枚举码。
 * INT-1480 P2-1：本抽屉全部 Select 逐个补齐（选项与 SelectContent 子项同源常量）。
 */
const TEST_DEVICE_TYPE_OPTIONS = [
  { value: 'physical', label: '真机' },
  { value: 'http_api', label: 'HTTP API' },
  { value: 'websocket_api', label: 'Realtime WS' },
]
const PLAYBACK_DEVICE_TYPE_OPTIONS = [
  { value: 'dry', label: '干声设备' },
  { value: 'noise', label: '噪声设备' },
]
const CONNECTION_TYPE_OPTIONS = [
  { value: 'usb', label: 'USB连接' },
  { value: 'remote', label: '远程连接' },
]
const PRIORITY_OPTIONS = Array.from({ length: 10 }, (_, i) => ({
  value: String(i + 1),
  label: String(i + 1),
}))

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

/** 两页签表单 schema（§6.2 分叉；z.discriminatedUnion 单 useForm 承载）。
 * 用 extend 而非展开 shape：保留各页签 schema 的 superRefine（如代理跨字段校验）。
 * INT-2153：API 分支已移出抽屉（走 §5.3 API 编辑弹窗），此处只剩测试设备 / 播放设备。 */
const deviceFormSchema = z.discriminatedUnion('kind', [
  testDeviceFormSchema.extend({ kind: z.literal('test') }),
  playbackDeviceFormSchema.extend({ kind: z.literal('playback') }),
])

type DeviceForm = z.infer<typeof deviceFormSchema>

function buildDefaults(
  state: DeviceMutateState,
  prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> | null | undefined
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
      needsPromptAudio: device?.needsPromptAudio ?? false,
      algorithms: device?.supportedAlgorithms ?? [],
      tags: device?.tags ?? [],
      customAttributes: (device?.customAttributes ?? []).join(', '),
      priority: String(device?.priority ?? 5),
    }
  }
  const device = state.mode === 'edit' ? (state.device as PlaybackDevice | null) : null
  // P2-2 返修：播放扫描「添加」预填透传（§6.1 playback: name/model/deviceUniqueId/channelIndex/
  // sampleRate/deviceType；对齐 test 分支 scanPrefill 口径）
  const scanPrefill = prefill as Partial<PlaybackDevice> | null
  return {
    kind: 'playback',
    name: device?.name ?? scanPrefill?.name ?? '',
    description: device?.description ?? '',
    model: device?.model ?? scanPrefill?.model ?? '',
    deviceType: device?.deviceType ?? scanPrefill?.deviceType ?? 'dry',
    deviceUniqueId: device?.deviceUniqueId ?? scanPrefill?.deviceUniqueId ?? '',
    channelIndex: String(device?.channelIndex ?? scanPrefill?.channelIndex ?? 0),
    supportedChannels: device?.supportedChannels != null ? String(device.supportedChannels) : '',
    supportedFormats: device?.supportedFormats ?? [],
    sampleRate: String(device?.sampleRate ?? scanPrefill?.sampleRate ?? 48000),
    splMappingId: device?.currentSplMappingId != null ? String(device.currentSplMappingId) : '',
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
  const { createTest, updateTest, createPlayback, updatePlayback } = useDeviceMutations()
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
  const { options: algorithmRawOptions, canRead: canReadAlgorithm } = useAlgorithmOptions()
  const algorithmOptions = useMemo(
    () => algorithmRawOptions.map((o) => ({ value: o.value, label: o.name })),
    [algorithmRawOptions]
  )
  const form = useForm<DeviceForm>({
    resolver: zodResolver(deviceFormSchema),
    values: buildDefaults(state, prefill),
  })

  // INT-1029 抽屉内扫描「选择」→ 回填当前表单（编辑/新增态均可用；nonce 递增触发）
  useEffect(() => {
    if (scanFill && state.open && scanFill.kind === kind) {
      mergeScanPrefill(form, scanFill.kind, scanFill.prefill)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanFill?.nonce])

  const [saving, setSaving] = useState(false)

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
      }
      toast.success(kind === 'test' ? '测试设备已保存' : '播放设备已保存')
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
            登记或修改{kind === 'test' ? '测试设备' : '播放设备'}信息。
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
                  placeholder={kind === 'test' ? '如：测试机-1号位' : '如：音箱-客厅位'}
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
                      items={TEST_DEVICE_TYPE_OPTIONS}
                      onValueChange={(value) => form.setValue('deviceType', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TEST_DEVICE_TYPE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='设备系统' required error={errors.system?.message}>
                    <Select
                      value={form.watch('system')}
                      items={SYSTEM_OPTIONS}
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
                        items={(form.watch('system') === 'HarmonyOS'
                          ? HARMONY_API_LEVELS
                          : ANDROID_API_LEVELS
                        ).map((level) => ({ value: level, label: `API ${level}` }))}
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
                      items={CONNECTION_TYPE_OPTIONS}
                      onValueChange={(value) => form.setValue('connectionType', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {CONNECTION_TYPE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label='设备序列号' required error={errors.serialNumber?.message}>
                    <Input {...form.register('serialNumber')} placeholder='连接后自动填充' className='h-8' />
                  </Field>
                  {/* 远程连接 IP（P3-1：原「端口」输入移除——后端 DeviceCreate/UpdateSchema 与
                      DeviceItem 均无 port 字段，提交即丢且无法回显；ADR 见交付评论） */}
                  {form.watch('connectionType') === 'remote' && (
                    <Field label='IP 地址'>
                      <Input {...form.register('ip')} placeholder='192.168.x.x' className='h-8' />
                    </Field>
                  )}
                  {/* 驱动关键字（V9.7.10 添加测试设备 keywords 选填；GET /test-devices/driver-keywords 真实选项，INT-721 接线） */}
                  <Field label='驱动关键字' className='col-span-2'>
                    <Select
                      value={form.watch('keywords') ?? ''}
                      items={[
                        { value: '', label: '不使用驱动关键字' },
                        ...driverKeywords.map((kw) => ({
                          value: kw.keywords,
                          label: `${kw.name}（${kw.system}）`,
                        })),
                      ]}
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
                          items={PRIORITY_OPTIONS}
                          onValueChange={(value) => form.setValue('priority', value ?? '5')}
                        >
                          <SelectTrigger size='sm' className='w-full'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PRIORITY_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
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
                      items={PLAYBACK_DEVICE_TYPE_OPTIONS}
                      onValueChange={(value) => form.setValue('deviceType', value ?? '')}
                    >
                      <SelectTrigger size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PLAYBACK_DEVICE_TYPE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
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
                      items={[
                        { value: '', label: '不使用声压映射' },
                        ...splOptions.map((mapping) => ({
                          value: String(mapping.id),
                          label: `${mapping.name}（${mapping.calibrationStatus === 'calibrated' ? '已校准' : '未校准'}）`,
                        })),
                      ]}
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

/** 抽屉标题（INT-2153：测试 API 不在本抽屉，标题映射只剩两类设备） */
const DEVICE_ADD_TITLE: Record<'test' | 'playback', string> = {
  test: '添加测试设备',
  playback: '添加播放设备',
}
