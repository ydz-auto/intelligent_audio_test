/**
 * 扫描设备弹窗（16_设备域.md §6.1；Dialog sm:max-w-3xl）。
 * 顶部扫描进度条（Progress + 「{pct}% - {scanStatus}」，scanStatus 分档：正在初始化扫描.../
 * 正在扫描测试设备.../正在获取系统音频设备.../正在扫描 API 服务.../扫描完成）；结果分区——
 * 测试设备（ADB/HDC 扫描）：系统图标 + name + 「{system} - {serial}」+ ip + 连接方式 +
 * 「添加」primary 钮（防重 3s）；播放设备（系统音频通道）：通道索引/采样率 + 添加；
 * API 服务：后端恒空 → 页签显空态「API 暂不支持自动扫描，请手动添加」（§11-11）。
 * 扫描结果行一律显示「添加」（后端 is_registered 恒 false，不按 serial 去重，可重复登记）；
 * 底部「开始扫描/扫描中...」；
 * 空态「未扫描到任何设备，请确保 ADB 设备已连接」；mock 兜底加 muted 提示「当前为模拟数据」。
 * 点「添加」→ 关扫描窗 + 开新增抽屉并预填扫描行字段（§6.1 注 / P2-13 返修）。
 * P2-2 返修：timer 用 useRef 持有，reset/关闭 clearInterval，杜绝并发双 interval。
 * INT-2074（开始测试页接线）：selectMode 双扫（test + playback）——每行 Checkbox 勾选，
 * 「加入设备选择」回传 DeviceScanSelection，未注册设备由 application 层登记后进设备网格。
 */
import { Smartphone, AudioLines, Ban } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

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
import { Progress } from '@/features/tasks/components/ui/progress'
import { normalizeDeviceSystem } from '@/features/devices/lib/device-system'
import { useDeviceMutations } from '@/application/devices/use-devices'
import type { DeviceScanRow, DeviceScanSelection } from '@/domain/models/deviceScan'
import { resolveScanConnectionType } from '@/domain/models/deviceScan'
import type { DevicesTabKey } from '@/features/devices/constants'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'

export interface ScanDevicesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 设备管理页用法（§6.1 必填）：单页签扫描 + 添加/选择；selectMode 时忽略 */
  tab?: DevicesTabKey
  onAddToMutate?: (
    kind: DevicesTabKey,
    prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice>
  ) => void
  /** INT-1029 抽屉内扫描回填：允许选择已注册设备（编辑态回填当前表单，按钮「选择」） */
  fillMode?: boolean
  /** INT-2074 开始测试页用法：test + playback 双扫、Checkbox 勾选 → onConfirmSelection */
  selectMode?: boolean
  onConfirmSelection?: (selection: DeviceScanSelection) => void
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
  const [rows, setRows] = useState<DeviceScanRow[]>([])
  const [adding, setAdding] = useState<Set<number>>(new Set())
  // INT-2074 selectMode：双扫结果 + 勾选索引集
  const [testRows, setTestRows] = useState<DeviceScanRow[]>([])
  const [playbackRows, setPlaybackRows] = useState<DeviceScanRow[]>([])
  const [checkedTest, setCheckedTest] = useState<Set<number>>(new Set())
  const [checkedPlayback, setCheckedPlayback] = useState<Set<number>>(new Set())
  const timerRef = useRef<number | null>(null)
  const { scan } = useDeviceMutations()
  const fillMode = props.fillMode === true
  const selectMode = props.selectMode === true

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
    setTestRows([])
    setPlaybackRows([])
    setAdding(new Set())
    setCheckedTest(new Set())
    setCheckedPlayback(new Set())
  }

  const handleScan = () => {
    // 防重入：已扫描中不重复启动
    if (scanning) return
    clearTimer()
    // 接线 INT-644：进度为 UX 分档状态机（§6.1 scanStatus），100% 时调真实 scan 端点
    setScanning(true)
    setProgress(0)
    // INT-2074：selectMode 双扫 test + playback；设备管理页单扫（API 页签无扫描源，footer 隐藏）
    const kinds: Array<'test' | 'playback'> = selectMode
      ? ['test', 'playback']
      : [props.tab === 'test' ? 'test' : 'playback']
    if (selectMode) {
      // 重新扫描：清空上一轮结果与勾选（避免旧索引映射到新结果）
      setTestRows([])
      setPlaybackRows([])
      setCheckedTest(new Set())
      setCheckedPlayback(new Set())
    }
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
            if (selectMode) {
              const [testResult, playbackResult] = await Promise.all([
                scan.mutateAsync('test'),
                scan.mutateAsync('playback'),
              ])
              setTestRows((testResult ?? []) as DeviceScanRow[])
              setPlaybackRows((playbackResult ?? []) as DeviceScanRow[])
            } else {
              const result = await scan.mutateAsync(kinds[0])
              setRows((result ?? []) as DeviceScanRow[])
            }
          } catch {
            setRows([])
            setTestRows([])
            setPlaybackRows([])
            toast.error('扫描失败，请检查后端设备服务')
          }
        })()
      }
    }, 350)
  }

  // P3-2 返修：V9.7.10 autoStartScan:true —— 打开扫描弹窗即自动开始扫描（API 页签无扫描源跳过；
  // handleScan 内部 scanning 防重入，用户手动重扫不受影响）
  useEffect(() => {
    if (props.open && (selectMode || props.tab !== 'api')) {
      handleScan()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open, props.tab, selectMode])

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
            connectionType: resolveScanConnectionType(row ?? {}).value,
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
    props.onAddToMutate?.(props.tab as DevicesTabKey, prefill)
    toast.success(fillMode ? '已回填设备信息，可修改后保存' : '已添加到设备登记表单，请补充信息后保存')
  }

  const toggleChecked = (set: Set<number>, index: number, checked: boolean): Set<number> => {
    const next = new Set(set)
    if (checked) next.add(index)
    else next.delete(index)
    return next
  }

  const selectedCount = checkedTest.size + checkedPlayback.size

  const handleConfirmSelection = () => {
    if (selectedCount === 0) return
    const test = [...checkedTest]
      .map((i) => testRows[i])
      .filter((r): r is DeviceScanRow => Boolean(r))
    const playback = [...checkedPlayback]
      .map((i) => playbackRows[i])
      .filter((r): r is DeviceScanRow => Boolean(r))
    props.onConfirmSelection?.({ test, playback })
    reset()
    props.onOpenChange(false)
  }

  const stageIndex = Math.min(Math.floor(progress / 25), SCAN_STAGES.length - 1)
  const isApi = !selectMode && props.tab === 'api'

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
            {selectMode
              ? '扫描设备'
              : `扫描${props.tab === 'test' ? '测试' : props.tab === 'playback' ? '播放' : 'API'}设备`}
          </DialogTitle>
          <DialogDescription>
            {isApi
              ? 'API 服务暂无自动扫描数据源，请手动添加。'
              : selectMode
                ? '自动发现已连接的 ADB/HDC 设备与系统音频通道，勾选后加入设备选择。'
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
          ) : selectMode ? (
            <div className='flex flex-col gap-3'>
              {/* 测试设备（ADB/HDC） */}
              <section className='space-y-2'>
                <h4 className='text-sm font-semibold'>
                  测试设备
                  <span className='text-muted-foreground ms-2 text-xs font-normal'>
                    {testRows.length} 个在线设备
                  </span>
                </h4>
                {testRows.length === 0 ? (
                  <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed px-3 py-3 text-xs'>
                    {scanning ? '扫描中，请稍候…' : '未扫描到测试设备，请确保 ADB 设备已连接'}
                  </p>
                ) : (
                  <div className='flex flex-col gap-2'>
                    {testRows.map((row, index) => {
                      const title = row.name ?? row.serial ?? '未知设备'
                      return (
                        <div
                          key={row.serial ?? row.device_unique_id ?? index}
                          className='bg-card/50 flex flex-wrap items-center gap-2 rounded-lg border p-2.5'
                        >
                          <Smartphone aria-hidden='true' className='text-muted-foreground size-4' />
                          <span className='min-w-0 flex-1'>
                            <span className='block truncate text-sm font-medium'>{title}</span>
                            <span className='text-muted-foreground block text-xs'>
                              {`${normalizeDeviceSystem(row.system)?.label ?? row.system ?? '未知系统'} - ${row.serial ?? '—'} · ${resolveScanConnectionType(row).label}`}
                              {row.ip ? ` · ${row.ip}` : ''}
                            </span>
                          </span>
                          <label className='flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground'>
                            <Checkbox
                              checked={checkedTest.has(index)}
                              aria-label={`选择测试设备 ${title}`}
                              className='size-4'
                              onCheckedChange={(c) =>
                                setCheckedTest((prev) => toggleChecked(prev, index, Boolean(c)))
                              }
                            />
                            选择
                          </label>
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>

              {/* 播放通道（系统音频） */}
              <section className='space-y-2'>
                <h4 className='text-sm font-semibold'>
                  播放通道
                  <span className='text-muted-foreground ms-2 text-xs font-normal'>
                    {playbackRows.length} 个在线通道
                  </span>
                </h4>
                {playbackRows.length === 0 ? (
                  <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed px-3 py-3 text-xs'>
                    {scanning ? '扫描中，请稍候…' : '未扫描到播放通道'}
                  </p>
                ) : (
                  <div className='flex flex-col gap-2'>
                    {playbackRows.map((row, index) => {
                      const title = row.name ?? row.device_unique_id ?? '未知通道'
                      return (
                        <div
                          key={row.device_unique_id ?? index}
                          className='bg-card/50 flex flex-wrap items-center gap-2 rounded-lg border p-2.5'
                        >
                          <AudioLines aria-hidden='true' className='text-muted-foreground size-4' />
                          <span className='min-w-0 flex-1'>
                            <span className='block truncate text-sm font-medium'>{title}</span>
                            <span className='text-muted-foreground block text-xs'>
                              {`通道 ${row.channel_index ?? 0} · ${row.sample_rate ?? 48000} Hz`}
                            </span>
                          </span>
                          <label className='flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground'>
                            <Checkbox
                              checked={checkedPlayback.has(index)}
                              aria-label={`选择播放通道 ${title}`}
                              className='size-4'
                              onCheckedChange={(c) =>
                                setCheckedPlayback((prev) => toggleChecked(prev, index, Boolean(c)))
                              }
                            />
                            选择
                          </label>
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>

              <p className='text-muted-foreground text-xs'>
                勾选设备后点击「加入设备选择」：未注册设备将自动登记，随后出现在设备网格（在线态），可直接勾选进入下一步。
              </p>
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
                          ? `${normalizeDeviceSystem(row.system)?.label ?? row.system ?? '未知系统'} - ${row.serial ?? '—'} · ${resolveScanConnectionType(row).label}`
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
                  : '扫描行均显示「添加」，同一序列号可重复登记（§6.1）'}
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          {selectMode ? (
            <>
              <Button variant='outline' disabled={scanning} onClick={handleScan}>
                重新扫描
              </Button>
              <Button disabled={scanning || selectedCount === 0} onClick={handleConfirmSelection}>
                加入设备选择（{selectedCount}）
              </Button>
            </>
          ) : (
            !isApi && (
              <Button disabled={scanning} onClick={handleScan}>
                {scanning ? '扫描中...' : '开始扫描'}
              </Button>
            )
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
