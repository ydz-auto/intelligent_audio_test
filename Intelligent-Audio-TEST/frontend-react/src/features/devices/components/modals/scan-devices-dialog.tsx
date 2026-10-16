/**
 * 扫描设备弹窗（16_设备域.md §6.1；Dialog sm:max-w-3xl）。
 * 顶部扫描进度条（Progress + 「{pct}% - {scanStatus}」，scanStatus 分档：正在初始化扫描.../
 * 正在扫描测试设备.../正在获取系统音频设备.../正在扫描 API 服务.../扫描完成）；结果分区——
 * 测试设备（ADB/HDC 扫描）：系统图标 + name + 「{system} - {serial}」+ ip + 连接方式 +
 * 「添加」primary 钮（防重 3s）；播放设备（系统音频通道）：通道索引/采样率 + 添加；
 * API 服务：后端恒空 → 页签显空态「API 暂不支持自动扫描，请手动添加」（§11-11）。
 * 已注册设备行显「已添加」muted 徽标 + 添加钮禁用；底部「开始扫描/扫描中...」；
 * 空态「未扫描到任何设备，请确保 ADB 设备已连接」；mock 兜底加 muted 提示「当前为模拟数据」。
 * 点「添加」→ 关扫描窗 + 开新增抽屉预填（§6.1 注）。
 */
import { Smartphone, AudioLines, Ban } from 'lucide-react'
import { useState } from 'react'
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
import type { DevicesTabKey } from '@/features/devices/constants'

export interface ScanDevicesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tab: DevicesTabKey
  onAddToMutate: (kind: DevicesTabKey) => void
}

/** 扫描结果行（device.py DeviceScanItem / playback.py PlaybackScanItem） */
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

  const reset = () => {
    setProgress(0)
    setScanning(false)
    setRows([])
    setAdding(new Set())
  }

  const handleScan = () => {
    // 模拟分档进度（§6.1 scanStatus 状态机）；接线后接 useDeviceMutations().scan
    setScanning(true)
    setProgress(0)
    const kind = props.tab === 'test' ? 'test' : 'playback'
    const timer = window.setInterval(() => {
      setProgress((prev) => {
        const next = Math.min(100, prev + 25)
        if (next >= 100) {
          window.clearInterval(timer)
          setScanning(false)
          // mock 扫描结果（§6.1 mock 兜底）
          setRows(
            kind === 'test'
              ? [
                  { name: '音箱-扫描新机', model: '旗舰 S1', serial: 'SN-SCAN-1001', system: 'harmony', system_version: '3.2.1', ip: '192.168.1.51', status: 'online', is_registered: false, id: null, type: 'physical' },
                  { name: '手机-扫描小米14', model: 'Xiaomi 14', serial: 'SN-SCAN-1002', system: 'android', system_version: '14', ip: '192.168.1.52', status: 'online', is_registered: false, id: null, type: 'physical' },
                  { name: '音箱-客厅位', model: '旗舰 S1', serial: 'SN-A001-8821', system: 'harmony', system_version: '3.2.1', ip: '192.168.1.21', status: 'online', is_registered: true, id: 1, type: 'physical' },
                ]
              : [
                  { name: 'Speaker Out 1', model: '系统音频通道', device_unique_id: 'AUDIO-OUT-01', channel_index: 0, sample_rate: 48000, type: 'dry', status: 'online' },
                  { name: 'Speaker Out 2', model: '系统音频通道', device_unique_id: 'AUDIO-OUT-02', channel_index: 1, sample_rate: 48000, type: 'noise', status: 'offline' },
                ]
          )
        }
        return next
      })
    }, 350)
  }

  const handleAdd = (index: number) => {
    if (adding.has(index)) return
    setAdding((prev) => new Set(prev).add(index))
    props.onAddToMutate(props.tab)
    toast.success('已添加到设备登记表单，请补充信息后保存')
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
                          ? `${row.system ?? '未知系统'} - ${row.serial ?? '—'}`
                          : `通道 ${row.channel_index ?? 0} · ${row.sample_rate ?? 48000} Hz`}
                        {row.ip ? ` · ${row.ip}` : ''}
                      </span>
                    </span>
                    {registered ? (
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
                        {adding.has(index) ? '已添加…' : '添加'}
                      </Button>
                    )}
                  </div>
                )
              })}
              <p className='text-muted-foreground text-xs'>
                当前为模拟数据（§6.1 mock 兜底；无真机时后端 scan 亦返 mock 列表）
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
