/**
 * 导出设备弹窗（16_设备域.md §4.5.2；页面设计文档 §4.5.2；INT-1624 接线 INT-816）。
 * 导出格式 Select（JSON / Excel，默认 JSON）+ 导出范围 Radio
 * （全部 / 当前页选中 / 当前筛选结果——页面已是全量拉取 + 前端筛选分页，
 * 三者分别映射为不带 ids / 选中 ids / 筛选后 ids）+ 主钮「导出」→ 文件流直接存盘。
 * 后端无字段勾选与「高级选项」能力（ResourceExportQuery 仅 ids/format），按实际契约裁剪。
 * 关闭即清空格式、范围、错误与下载态（重开无残留）；页签切换由页面层 key={tab} 重挂复位，
 * 取消 / Esc / 切页签三条关闭路径重开都是空态。
 */
import { Download } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { ApiError } from '@/infrastructure/api/api-error'
import { exportDeviceResource } from '@/infrastructure/api/devicesApi'
import type { DeviceExportFormat, DeviceExportRange } from '@/domain/models/deviceImportExport'
import {
  DEVICES_EXPORT_FORMAT_OPTIONS,
  DEVICES_EXPORT_RANGE_OPTIONS,
  DEVICES_RESOURCE_LABEL,
  type DevicesTabKey,
} from '@/features/devices/constants'

export interface ExportDevicesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tab: DevicesTabKey
  /** 当前勾选 id（含跨页选择；「当前页选中」范围） */
  selectedIds: number[]
  /** 当前筛选结果 id（「当前筛选结果」范围） */
  filteredIds: number[]
}

/** 触发浏览器下载（Blob → <a download>；与 test-execution-api / 任务导出同口径） */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export function ExportDevicesDialog({
  open,
  onOpenChange,
  tab,
  selectedIds,
  filteredIds,
}: ExportDevicesDialogProps) {
  const [format, setFormat] = useState<DeviceExportFormat>('json')
  const [range, setRange] = useState<DeviceExportRange>('all')
  const [exporting, setExporting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const label = DEVICES_RESOURCE_LABEL[tab]
  const rangeCount: Record<DeviceExportRange, number> = {
    all: -1,
    selected: selectedIds.length,
    filtered: filteredIds.length,
  }
  /** 范围无数据时不发起导出（避免空 id 集被后端当作全量/空文件） */
  const rangeEmpty = range !== 'all' && rangeCount[range] === 0

  const handleOpenChange = (next: boolean) => {
    onOpenChange(next)
    if (!next) {
      setFormat('json')
      setRange('all')
      setExporting(false)
      setErrorMessage('')
    }
  }

  const startExport = async () => {
    if (exporting || rangeEmpty) return
    setErrorMessage('')
    setExporting(true)
    try {
      const ids =
        range === 'selected' ? selectedIds : range === 'filtered' ? filteredIds : undefined
      const { blob, filename } = await exportDeviceResource(tab, { format, ids })
      downloadBlob(blob, filename)
      toast.success(`导出完成：${filename}`)
      handleOpenChange(false)
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? (error.userMessage || error.message) : '导出失败，请稍后重试'
      )
    } finally {
      setExporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>导出{label}</DialogTitle>
          <DialogDescription>选择格式与范围，导出文件直接下载</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='flex items-center justify-between gap-2'>
            <span className='text-sm font-medium'>导出格式</span>
            <Select
              value={format}
              items={[...DEVICES_EXPORT_FORMAT_OPTIONS]}
              onValueChange={(value) => setFormat((value as DeviceExportFormat) ?? 'json')}
            >
              <SelectTrigger size='sm' className='h-8 w-40'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEVICES_EXPORT_FORMAT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <fieldset className='space-y-1'>
            <legend className='mb-1 text-sm font-medium'>导出范围</legend>
            {DEVICES_EXPORT_RANGE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'
              >
                <input
                  type='radio'
                  name='device-export-range'
                  value={option.value}
                  checked={range === option.value}
                  onChange={() => setRange(option.value)}
                />
                {option.label}
                {option.value !== 'all' && (
                  <span className='text-muted-foreground text-xs tabular-nums'>
                    （{rangeCount[option.value]} 个）
                  </span>
                )}
              </label>
            ))}
          </fieldset>

          {rangeEmpty && (
            <p className='text-muted-foreground text-xs'>
              {range === 'selected' ? '尚未勾选设备，请先勾选' : '当前筛选结果为空'}
            </p>
          )}
          {errorMessage && <p className='text-destructive text-xs'>{errorMessage}</p>}
        </div>

        <DialogFooter>
          <Button variant='outline' disabled={exporting} onClick={() => handleOpenChange(false)}>
            取消
          </Button>
          <Button disabled={exporting || rangeEmpty} onClick={() => void startExport()}>
            {exporting ? (
              <>
                <Spinner size={14} className='text-current' />
                正在导出…
              </>
            ) : (
              <>
                <Download aria-hidden='true' className='size-3.5' />
                导出
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
