/**
 * 扫描设备弹窗（16_设备域.md §6.1；Dialog sm:max-w-3xl）。
 * 顶部扫描进度条（Progress + 「{pct}% - {scanStatus}」，scanStatus 分档：正在初始化扫描.../
 * 正在扫描测试设备.../正在获取系统音频设备.../正在扫描 API 服务.../扫描完成）；结果分区——
 * 测试设备（ADB/HDC 扫描）：系统图标 + name + 「{system} - {serial}」+ ip + 连接方式 +
 * 「添加」primary 钮（防重 3s）；播放设备（系统音频通道）：通道索引/采样率 + 添加；
 * API 服务：后端恒空 → 页签显空态「API 暂不支持自动扫描，请手动添加」（§11-11）。
 * 已注册设备行显「已添加」muted 徽标 + 添加钮禁用；底部「开始扫描/扫描中...」；
 * 空态「未扫描到任何设备，请确保 ADB 设备已连接」；mock 兜底加 muted 提示「当前为模拟数据」。
 * 点「添加」→ 关扫描窗 + 开新增抽屉并预填扫描行字段（§6.1 注 / P2-13 返修）。
 * P2-2 返修：timer 用 useRef 持有，reset/关闭 clearInterval，杜绝并发双 interval。
 */
import { Smartphone, AudioLines, Ban } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

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
import { Progress } from '@/features/tasks/components/ui/progress'
import { normalizeDeviceSystem } from '@/features/devices/lib/device-system'
import { useDeviceMutations } from '@/application/devices/use-devices'
import type { DevicesTabKey } from '@/features/devices/constants'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'

export interface ScanDevicesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tab: DevicesTabKey
  /** §6.1 扫描「添加」→ 开新增抽屉并预填扫描行字段（P2-13：透传行数据） */
  onAddToMutate: (
    kind: DevicesTabKey,
    prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice>
  ) => void
  /** INT-1029 抽屉内扫描回填：允许选择已注册设备（编辑态回填当前表单，按钮「选择」） */
  fillMode?: boolean
}

/** 扫描结果行（device.py DeviceScanItem / playback.py PlaybackScanItem，snake_case 直出） */
interface ScanResultRow {
  name?: string | null
  model?: string | null
  serial?: string | null
  system?: string | null
  system_version?: string | null
  ip?: string | null
  status?: string | null
  is_registered?: boolean
  id?: number | string | null
  device_unique_id?: string | null
  channel_index?: number | null
  sample_rate?: number | null
  type?: string | null
  /** P3-1 返修：后端扫描响应透传真实应用名/版本，预填不再硬编码默认值 */
  app_name?: string | null
  app_version?: string | null
  /** P3-2 返修：后端若透传连接方式则直用（device.py DeviceScanItem 当前未含，按序列号/IP 兜底判定） */
  connection_type?: string | null
  connectionType?: string | null
}

/** 连接方式判定（§6.1/V9.7.10 ScanDevicesModal.vue:27-29）：
 * 后端透传 connection_type 优先；未透传时按 adb 远程序列号形态（host:port）或 ip 判定，
 * 否则按 USB 连接（与设备列表「连接方式」列同口径）。 */
function resolveConnectionType(row: ScanResultRow): { value: 'usb' | 'remote'; label: string } {
  const raw = row.connection_type ?? row.connectionType
  if (raw === 'usb') return { value: 'usb', label: 'USB连接' }
  if (raw === 'remote') return { value: 'remote', label: '远程连接' }
  if ((row.serial ?? '').includes(':') || row.ip) return { value: 'remote', label: '远程连接' }
  return { value: 'usb', label: 'USB连接' }
}

const SCAN_STAGES: ReadonlyArray<string> = [
  '正在初始化扫描...',
  '正在扫描测试设备...',
  '正在获取系统音频设备...',
  '正在扫描 API 服务...',
  '扫描完成',
]

export function ScanDevicesDialog(props: ScanDevicesDialogProps) {
  const [progress, setProgress] = useState(0)
  const [scanning, setScanning] = useState(false)
  const [rows, setRows] = useState<ScanResultRow[]>([])
  const [adding, setAdding] = useState<Set<number>>(new Set())
  const timerRef = useRef<number | null>(null)
  const { scan } = useDeviceMutations()
  const fillMode = props.fillMode === true

  const clearTimer = () => {
    if (timerRef.current != null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  const reset = () => {
    clearTimer()
    setProgress(0)
    setScanning(false)
    setRows([])
    setAdding(new Set())
  }

  const handleScan = () => {
    // 防重入：已扫描中不重复启动
    if (scanning) return
    clearTimer()
    // 接线 INT-644：进度为 UX 分档状态机（§6.1 scanStatus），100% 时调真实 scan 端点
    setScanning(true)
    setProgress(0)
    const kind = props.tab === 'test' ? 'test' : 'playback'
    // P2-2 返修：updater 不做副作用——完成逻辑放 interval 回调（tick 计数驱动）
    let tick = 0
    timerRef.current = window.setInterval(() => {
      tick += 1
      const next = Math.min(100, tick * 25)
      setProgress(next)
      if (next >= 100) {
        clearTimer()
        setScanning(false)
        void (async () => {
          try {
            const result = await scan.mutateAsync(kind)
            setRows((result ?? []) as ScanResultRow[])
          } catch {
            setRows([])
            toast.error('扫描失败，请检查后端设备服务')
          }
        })()
      }
    }, 350)
  }

  // P3-2 返修：V9.7.10 autoStartScan:true —— 打开扫描弹窗即自动开始扫描（API 页签无扫描源跳过；
  // handleScan 内部 scanning 防重入，用户手动重扫不受影响）
  useEffect(() => {
    if (props.open && props.tab !== 'api') {
      handleScan()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open, props.tab])

  const handleAdd = (index: number) => {
    if (adding.has(index)) return
    setAdding((prev) => new Set(prev).add(index))
    const row = rows[index]
    // §6.1：预填扫描行字段（test: name/model/serialNumber/system归一/systemVersion/appName/appVersion/ip；
    // playback: name/model/deviceUniqueId/channelIndex/sampleRate/deviceType）
    const prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> =
      props.tab === 'test'
        ? {
            name: row?.name ?? '',
            model: row?.model ?? '',
            serialNumber: row?.serial ?? '',
            system: normalizeDeviceSystem(row?.system)?.label ?? 'Android',
            systemVersion: row?.system_version ?? '未知',
            ip: row?.ip ?? '',
            connectionType: resolveConnectionType(row ?? {}).value,
            // P3-1 返修：透传扫描响应真实应用名/版本（V9.7.10 `appName || 'Default App'` 口径）
            appName: row?.app_name ?? 'Default App',
            appVersion: row?.app_version ?? '1.0.0',
          }
        : {
            name: row?.name ?? '',
            model: row?.model ?? '',
            deviceUniqueId: row?.device_unique_id ?? '',
            channelIndex: row?.channel_index ?? 0,
            sampleRate: row?.sample_rate ?? 48000,
            deviceType: (row?.type as PlaybackDevice['deviceType']) ?? 'dry',
          }
    props.onAddToMutate(props.tab, prefill)
    toast.success(fillMode ? '已回填设备信息，可修改后保存' : '已添加到设备登记表单，请补充信息后保存')
  }

  const stageIndex = Math.min(Math.floor(progress / 25), SCAN_STAGES.length - 1)
  const isApi = props.tab === 'api'

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        if (!open) reset()
        props.onOpenChange(open)
      }}
    >
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>
            扫描{props.tab === 'test' ? '测试' : props.tab === 'playback' ? '播放' : 'API'}设备
          </DialogTitle>
          <DialogDescription>
            {isApi
              ? 'API 服务暂无自动扫描数据源，请手动添加。'
              : '自动发现已连接的 ADB/HDC 设备或系统音频通道。'}
          </DialogDescription>
        </DialogHeader>

        <div className='flex flex-col gap-3'>
          {/* 扫描进度条（§6.1） */}
          <div className='flex items-center gap-2'>
            <Progress value={progress} size='xs' className='flex-1' />
            <span className='text-muted-foreground w-44 text-xs tabular-nums'>
              {progress}% - {SCAN_STAGES[stageIndex]}
            </span>
          </div>

          {isApi ? (
            <div className='text-muted-foreground border-border/60 flex items-center justify-center gap-2 rounded-lg border border-dashed py-10 text-sm'>
              <Ban aria-hidden='true' className='size-4' />
              API 暂不支持自动扫描，请手动添加
            </div>
          ) : rows.length === 0 ? (
            <div className='text-muted-foreground border-border/60 flex items-center justify-center rounded-lg border border-dashed py-10 text-sm'>
              {scanning ? '扫描中，请稍候…' : '未扫描到任何设备，请确保 ADB 设备已连接'}
            </div>
          ) : (
            <div className='flex flex-col gap-2'>
              {rows.map((row, index) => {
                const registered = Boolean(row.is_registered)
                return (
                  <div
                    key={row.serial ?? row.device_unique_id ?? index}
                    className='bg-card/50 flex flex-wrap items-center gap-2 rounded-lg border p-2.5'
                  >
                    {props.tab === 'test' ? (
                      <Smartphone aria-hidden='true' className='text-muted-foreground size-4' />
                    ) : (
                      <AudioLines aria-hidden='true' className='text-muted-foreground size-4' />
                    )}
                    <span className='min-w-0 flex-1'>
                      <span className='block truncate text-sm font-medium'>
                        {row.name ?? row.serial ?? row.device_unique_id ?? '未知设备'}
                      </span>
                      <span className='text-muted-foreground block text-xs'>
                        {props.tab === 'test'
                          ? `${normalizeDeviceSystem(row.system)?.label ?? row.system ?? '未知系统'} - ${row.serial ?? '—'} · ${resolveConnectionType(row).label}`
                          : `通道 ${row.channel_index ?? 0} · ${row.sample_rate ?? 48000} Hz`}
                        {row.ip ? ` · ${row.ip}` : ''}
                      </span>
                    </span>
                    {registered && !fillMode ? (
                      <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                        已添加
                      </Badge>
                    ) : (
                      <Button
                        size='sm'
                        className='h-7 gap-1 px-2.5 text-xs'
                        disabled={adding.has(index)}
                        onClick={() => handleAdd(index)}
                      >
                        {adding.has(index) ? (fillMode ? '已选择…' : '已添加…') : fillMode ? '选择' : '添加'}
                      </Button>
                    )}
                  </div>
                )
              })}
              <p className='text-muted-foreground text-xs'>
                {fillMode
                  ? '选择设备将回填登记表单（已注册设备也可选择，INT-1029）'
                  : '已注册设备显示「已添加」，可跳转登记表单补充信息后保存（§6.1）'}
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          {!isApi && (
            <Button disabled={scanning} onClick={handleScan}>
              {scanning ? '扫描中...' : '开始扫描'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
