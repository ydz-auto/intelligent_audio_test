/**
 * 设备新增/编辑抽屉（16_设备域.md §6.2；Sheet sideDrawer `sm:max-w-[600px]`）。
 * 分节「基本信息」（名称（必填）/描述）+ 分节随页签分叉：
 * - 测试设备：型号（必填）/设备类型（必填）/设备系统（必填，iOS·Android·HarmonyOS）/系统版本（必填）/
 *   应用名称（必填）/应用版本（必填）/连接方式（必填，USB连接·远程连接）/设备序列号（必填，选设备自动填充
 *   disabled）/IP地址·端口(conditional remote)/是否需要提示词(switch)/算法类型(多选 chips)/
 *   状态采集字段（只读：电池/存储/网络）/高级设置（Collapsible：备注/优先级）
 * - 播放设备：型号（必填）/设备类型（必填，干声·噪声）/系统唯一标识（必填，自动填充 disabled）/
 *   通道索引/支持的通道数/支持的格式(多选)/采样率/声压映射 select
 * - 测试 API：API名称（必填）/供应商/API 端点（必填，URL）/关联算法（必填）/API 元数据(协议+环境)/
 *   默认最大进程数/默认最大超时/默认最大音频时长（编辑复用 INT-355 §5.3 口径，字段以 INT-355 为准）
 * 提交前必填校验；成功 toast「{实体}已保存」+ 列表失效重拉（mock 内存库 invalidate）。
 * mock 阶段用受控 state 表单（对齐 audio-import modals 模式；接线后 RHF+zod 化）。
 */
import { ChevronDown, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

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
import { useDeviceMutations } from '@/application/devices/use-devices'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'

export interface DeviceMutateDrawerProps {
  state: DeviceMutateState
  onOpenChange: (open: boolean) => void
  /** 扫描预填（§6.1：测试设备 name/model/serialNumber/system 等） */
  prefill?: Partial<TestDevice> | null
}

const SYSTEM_OPTIONS = [
  { value: 'iOS', label: 'iOS' },
  { value: 'Android', label: 'Android' },
  { value: 'HarmonyOS', label: 'HarmonyOS' },
]

const FORMAT_OPTIONS = ['WAV', 'MP3', 'FLAC', 'AAC', 'OGG', 'WMA']
const ALGORITHM_OPTIONS = ['asr_streaming', 'wakeword_detect', 'tts_eval']

function Field({
  label,
  required,
  children,
  className,
}: {
  label: string
  required?: boolean
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
    </div>
  )
}

export function DeviceMutateDrawer(props: DeviceMutateDrawerProps) {
  const { state, prefill } = props
  const open = state.open
  const kind = state.kind
  const isEdit = state.mode === 'edit' && state.device != null
  const editingDevice = isEdit ? state.device : null
  const { createTest, updateTest, createPlayback, updatePlayback, createApi, updateApi } =
    useDeviceMutations()

  // mock 阶段受控表单（§6.2 字段子集；接线后 RHF+zod）
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [model, setModel] = useState('')
  const [deviceType, setDeviceType] = useState('physical')
  const [system, setSystem] = useState('Android')
  const [systemVersion, setSystemVersion] = useState('')
  const [appName, setAppName] = useState('')
  const [appVersion, setAppVersion] = useState('')
  const [connectionType, setConnectionType] = useState('usb')
  const [serialNumber, setSerialNumber] = useState('')
  const [ip, setIp] = useState('')
  const [port, setPort] = useState('5555')
  const [needsPrompt, setNeedsPrompt] = useState(false)
  const [algorithms, setAlgorithms] = useState<string[]>([])
  const [priority, setPriority] = useState('5')
  const [vendor, setVendor] = useState('')
  const [apiUrl, setApiUrl] = useState('')
  const [protocol, setProtocol] = useState('https')
  const [environment, setEnvironment] = useState('testing')
  const [maxProcess, setMaxProcess] = useState('5')
  const [maxTimeout, setMaxTimeout] = useState('30')
  const [maxAudioDuration, setMaxAudioDuration] = useState('60')
  const [supportedFormats, setSupportedFormats] = useState<string[]>([])
  const [channelIndex, setChannelIndex] = useState('0')
  const [sampleRate, setSampleRate] = useState('48000')
  const [saving, setSaving] = useState(false)

  // 打开/切换模式时预填（编辑回显 + 扫描预填 §6.1）
  useEffect(() => {
    if (!open) return
    setName(editingDevice?.name ?? prefill?.name ?? '')
    setDescription(editingDevice?.description ?? '')
    if (kind === 'test') {
      const device = editingDevice as TestDevice | null
      setModel(device?.model ?? prefill?.model ?? '')
      setSystem(device?.system ?? prefill?.system ?? 'Android')
      setSystemVersion(device?.systemVersion ?? prefill?.systemVersion ?? '')
      setAppName(device?.appName ?? '')
      setAppVersion(device?.appVersion ?? '')
      setConnectionType(device?.connectionType ?? 'usb')
      setSerialNumber(device?.serialNumber ?? prefill?.serialNumber ?? '')
      setIp(device?.ip ?? '')
      setNeedsPrompt(device?.needsPromptAudio ?? false)
      setAlgorithms(device?.supportedAlgorithms ?? [])
      setPriority('5')
    } else if (kind === 'playback') {
      const device = editingDevice as PlaybackDevice | null
      setModel(device?.model ?? '')
      setDeviceType(device?.deviceType ?? 'dry')
      setSerialNumber(device?.deviceUniqueId ?? '')
      setChannelIndex(String(device?.channelIndex ?? 0))
      setSampleRate(String(device?.sampleRate ?? 48000))
      setSupportedFormats(device?.supportedFormats ?? [])
    } else {
      const device = editingDevice as ApiDevice | null
      setVendor(device?.vendor ?? '')
      setApiUrl(device?.apiUrl ?? '')
      setProtocol(device?.protocol ?? 'https')
      setEnvironment(device?.environment ?? 'testing')
      setMaxProcess(String(device?.defaultMaxProcess ?? 5))
      setMaxTimeout(String(device?.defaultMaxTimeout ?? 30))
      setMaxAudioDuration(String(device?.defaultMaxAudioDuration ?? 60))
    }
  }, [open, kind, editingDevice, prefill])

  const toggleAlgorithm = (algo: string) => {
    setAlgorithms((prev) =>
      prev.includes(algo) ? prev.filter((a) => a !== algo) : [...prev, algo]
    )
  }

  const toggleFormat = (format: string) => {
    setSupportedFormats((prev) =>
      prev.includes(format) ? prev.filter((f) => f !== format) : [...prev, format]
    )
  }

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('请填写设备名称')
      return
    }
    setSaving(true)
    try {
      if (kind === 'test') {
        const base = {
          name: name.trim(),
          description: description || null,
          model: model || null,
          system,
          systemVersion: systemVersion || null,
          appName: appName || null,
          appVersion: appVersion || null,
          connectionType,
          serialNumber: serialNumber || null,
          ip: connectionType === 'remote' ? ip || null : null,
          needsPromptAudio: needsPrompt,
          supportedAlgorithms: algorithms.length > 0 ? algorithms : null,
          status: 'offline',
          type: deviceType,
          occupied: false,
          labId: null,
          labName: null,
          driverName: null,
          maxAudioDuration: null,
          location: null,
          keywords: null,
          lastOnlineAt: null,
        } satisfies Omit<TestDevice, 'id' | 'createdAt' | 'updatedAt'>
        if (isEdit) {
          await updateTest.mutateAsync({ id: editingDevice!.id, patch: base })
        } else {
          await createTest.mutateAsync(base)
        }
      } else if (kind === 'playback') {
        const base = {
          name: name.trim(),
          description: description || null,
          model: model || null,
          deviceType: (deviceType as PlaybackDevice['deviceType']),
          deviceUniqueId: serialNumber || null,
          sampleRate: Number(sampleRate) || 48000,
          channelIndex: Number(channelIndex) || 0,
          status: 'offline',
          currentSplMappingId: null,
          currentSplMappingName: null,
          occupied: false,
          labId: null,
          labName: null,
          supportedFormats: supportedFormats.length > 0 ? supportedFormats : null,
          supportedChannels: null,
          createdAt: null,
          updatedAt: null,
        } satisfies Omit<PlaybackDevice, 'id'>
        if (isEdit) {
          await updatePlayback.mutateAsync({ id: editingDevice!.id, patch: base })
        } else {
          await createPlayback.mutateAsync(base)
        }
      } else {
        const base = {
          name: name.trim(),
          description: description || null,
          vendor: vendor || null,
          apiUrl: apiUrl || null,
          status: 'offline',
          meta: { protocol, environment },
          protocol,
          environment,
          algorithmType: 'asr_streaming',
          defaultMaxProcess: Number(maxProcess) || 5,
          defaultMaxTimeout: Number(maxTimeout) || 30,
          defaultMaxAudioDuration: Number(maxAudioDuration) || 60,
          healthScore: null,
          endpoints: [],
          rmsSplMappingId: null,
          rmsSplMappingName: null,
          occupied: false,
          createdAt: null,
          updatedAt: null,
        } satisfies Omit<ApiDevice, 'id'>
        if (isEdit) {
          await updateApi.mutateAsync({ id: editingDevice!.id, patch: base })
        } else {
          await createApi.mutateAsync(base)
        }
      }
      toast.success(
        kind === 'test' ? '测试设备已保存' : kind === 'playback' ? '播放设备已保存' : '测试 API 已保存'
      )
      props.onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const title = isEdit ? '编辑设备' : DEVICE_ADD_TITLE[kind]

  return (
    <Sheet open={open} onOpenChange={props.onOpenChange}>
      <SheetContent className='sm:max-w-[600px]'>
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>登记或修改{kind === 'test' ? '测试设备' : kind === 'playback' ? '播放设备' : '测试 API'}信息。</SheetDescription>
        </SheetHeader>

        <div className='flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-2'>
          {/* 基本信息 */}
          <section className='flex flex-col gap-2'>
            <h3 className='text-sm font-medium'>基本信息</h3>
            <Field label='名称' required>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder='如：音箱-客厅位' className='h-8' />
            </Field>
            <Field label='描述'>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder='设备用途或工位说明' className='h-8' />
            </Field>
          </section>

          {kind === 'test' && (
            <section className='flex flex-col gap-2'>
              <h3 className='text-sm font-medium'>测试设备信息</h3>
              <div className='grid grid-cols-2 gap-2.5'>
                <Field label='型号' required>
                  <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder='如：旗舰 S1' className='h-8' />
                </Field>
                <Field label='设备类型' required>
                  <Select value={deviceType} onValueChange={(value) => setDeviceType(value ?? '')}>
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
                <Field label='设备系统' required>
                  <Select value={system} onValueChange={(value) => setSystem(value ?? '')}>
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
                <Field label='系统版本' required>
                  <Input value={systemVersion} onChange={(e) => setSystemVersion(e.target.value)} placeholder='如：12' className='h-8' />
                </Field>
                <Field label='应用名称'>
                  <Input value={appName} onChange={(e) => setAppName(e.target.value)} className='h-8' />
                </Field>
                <Field label='应用版本'>
                  <Input value={appVersion} onChange={(e) => setAppVersion(e.target.value)} className='h-8' />
                </Field>
                <Field label='连接方式' required>
                  <Select value={connectionType} onValueChange={(value) => setConnectionType(value ?? '')}>
                    <SelectTrigger size='sm' className='w-full'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='usb'>USB连接</SelectItem>
                      <SelectItem value='remote'>远程连接</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label='设备序列号' required>
                  <Input value={serialNumber} onChange={(e) => setSerialNumber(e.target.value)} disabled placeholder='连接后自动填充' className='h-8' />
                </Field>
                {connectionType === 'remote' && (
                  <>
                    <Field label='IP 地址'>
                      <Input value={ip} onChange={(e) => setIp(e.target.value)} placeholder='192.168.x.x' className='h-8' />
                    </Field>
                    <Field label='端口'>
                      <Input value={port} onChange={(e) => setPort(e.target.value)} type='number' className='h-8' />
                    </Field>
                  </>
                )}
              </div>
              <label className='flex items-center gap-2 text-sm'>
                <Switch size='sm' checked={needsPrompt} onCheckedChange={setNeedsPrompt} />
                是否需要提示词
              </label>
              <Field label='算法类型'>
                <div className='flex flex-wrap gap-1.5'>
                  {ALGORITHM_OPTIONS.map((algo) => (
                    <button
                      key={algo}
                      type='button'
                      onClick={() => toggleAlgorithm(algo)}
                      className={cn(
                        'rounded-md border px-2 py-1 text-xs transition-colors',
                        algorithms.includes(algo)
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'hover:bg-muted'
                      )}
                    >
                      {algo}
                    </button>
                  ))}
                </div>
              </Field>
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
              {/* 高级设置（§6.2 Collapsible 分区） */}
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
                      <Input value={description} onChange={(e) => setDescription(e.target.value)} className='h-8' />
                    </Field>
                    <Field label='优先级'>
                      <Select value={priority} onValueChange={(value) => setPriority(value ?? '')}>
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
                </CollapsibleContent>
              </Collapsible>
            </section>
          )}

          {kind === 'playback' && (
            <section className='flex flex-col gap-2'>
              <h3 className='text-sm font-medium'>播放设备信息</h3>
              <div className='grid grid-cols-2 gap-2.5'>
                <Field label='型号' required>
                  <Input value={model} onChange={(e) => setModel(e.target.value)} className='h-8' />
                </Field>
                <Field label='设备类型' required>
                  <Select value={deviceType} onValueChange={(value) => setDeviceType(value ?? '')}>
                    <SelectTrigger size='sm' className='w-full'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='dry'>干声设备</SelectItem>
                      <SelectItem value='noise'>噪声设备</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label='系统唯一标识' required>
                  <Input value={serialNumber} disabled placeholder='连接后自动填充' className='h-8' />
                </Field>
                <Field label='通道索引'>
                  <Input value={channelIndex} type='number' onChange={(e) => setChannelIndex(e.target.value)} className='h-8' />
                </Field>
                <Field label='采样率' required>
                  <Input value={sampleRate} type='number' onChange={(e) => setSampleRate(e.target.value)} className='h-8' />
                </Field>
              </div>
              <Field label='支持的格式'>
                <div className='flex flex-wrap gap-1.5'>
                  {FORMAT_OPTIONS.map((format) => (
                    <button
                      key={format}
                      type='button'
                      onClick={() => toggleFormat(format)}
                      className={cn(
                        'rounded-md border px-2 py-1 text-xs transition-colors',
                        supportedFormats.includes(format)
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'hover:bg-muted'
                      )}
                    >
                      {format}
                    </button>
                  ))}
                </div>
              </Field>
            </section>
          )}

          {kind === 'api' && (
            <section className='flex flex-col gap-2'>
              <h3 className='text-sm font-medium'>API 信息</h3>
              <div className='grid grid-cols-2 gap-2.5'>
                <Field label='供应商'>
                  <Input value={vendor} onChange={(e) => setVendor(e.target.value)} className='h-8' />
                </Field>
                <Field label='协议' required>
                  <Select value={protocol} onValueChange={(value) => setProtocol(value ?? '')}>
                    <SelectTrigger size='sm' className='w-full'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='http'>HTTP</SelectItem>
                      <SelectItem value='https'>HTTPS</SelectItem>
                      <SelectItem value='ws'>WS</SelectItem>
                      <SelectItem value='wss'>WSS</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label='环境'>
                  <Select value={environment} onValueChange={(value) => setEnvironment(value ?? '')}>
                    <SelectTrigger size='sm' className='w-full'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='development'>开发</SelectItem>
                      <SelectItem value='testing'>测试</SelectItem>
                      <SelectItem value='production'>生产</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label='默认最大进程数'>
                  <Input value={maxProcess} type='number' onChange={(e) => setMaxProcess(e.target.value)} className='h-8' />
                </Field>
                <Field label='默认最大超时（秒）'>
                  <Input value={maxTimeout} type='number' onChange={(e) => setMaxTimeout(e.target.value)} className='h-8' />
                </Field>
                <Field label='默认最大音频时长（秒）'>
                  <Input value={maxAudioDuration} type='number' onChange={(e) => setMaxAudioDuration(e.target.value)} className='h-8' />
                </Field>
              </div>
              <Field label='API 端点' required>
                <div className='flex items-center gap-1.5'>
                  <Input value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} placeholder='https://api.example.com/v1/asr' className='h-8 flex-1' />
                  <Button variant='outline' size='icon-sm' aria-label='添加端点' type='button'>
                    <Plus aria-hidden='true' />
                  </Button>
                </div>
              </Field>
              <p className='text-muted-foreground text-xs'>
                端点列表（优先级/最大进程/超时/音频时长）编辑复用 INT-355 §5.3 API 编辑弹窗口径。
              </p>
            </section>
          )}
        </div>

        <SheetFooter>
          <Button variant='outline' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={saving} onClick={() => void handleSave()}>
            {saving ? '保存中...' : '保存'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

const DEVICE_ADD_TITLE: Record<DevicesTabKey, string> = {
  test: '添加测试设备',
  playback: '添加播放设备',
  api: '添加测试API',
}
