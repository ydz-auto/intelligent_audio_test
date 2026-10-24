/**
 * 导入设备弹窗（16_设备域.md §4.5.1；页面设计文档 §4.5.1；INT-1624 接线 INT-816）。
 * 按当前页签取对应资源端点（测试设备 / 播放设备 / 测试 API 三对应同一套弹窗）。
 * 拖拽或点击选文件（.json/.csv/.xlsx）→「开始导入」→ 计数结果 + errors 行号列表。
 * 后端逐行提交、不整批回滚——部分成功是既定口径，结果区照实呈现；
 * 导出含 status 且导入会写回，故提示「设备状态以本环境为准」（口径 B）。
 * 关闭即清空文件、错误与结果（重开无残留）；页签切换由页面层 key={tab} 重挂复位，
 * 取消 / Esc / 切页签三条关闭路径重开都是空态。
 */
import { CheckCircle2, FileUp, UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'
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
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import { ApiError } from '@/infrastructure/api/api-error'
import { importDeviceResource } from '@/infrastructure/api/devicesApi'
import { formatImportSummary, type DeviceImportResult } from '@/domain/models/deviceImportExport'
import {
  DEVICES_IMPORT_ACCEPT,
  DEVICES_IMPORT_FORMAT_HINT,
  DEVICES_RESOURCE_LABEL,
  type DevicesTabKey,
} from '@/features/devices/constants'
import { cn } from '@/lib/utils'

export interface ImportDevicesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tab: DevicesTabKey
  /** 导入成功后刷新当前页签列表 / 顶部徽章 / 统计卡（页面层 invalidate） */
  onImported?: () => void
}

export function ImportDevicesDialog({ open, onOpenChange, tab, onImported }: ImportDevicesDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<DeviceImportResult | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const label = DEVICES_RESOURCE_LABEL[tab]

  /** 关闭即复位（下次打开无上次文件 / 结果残留） */
  const handleOpenChange = (next: boolean) => {
    onOpenChange(next)
    if (!next) {
      setFile(null)
      setDragging(false)
      setImporting(false)
      setResult(null)
      setErrorMessage('')
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const selectFile = (next: File | null | undefined) => {
    if (!next) return
    setFile(next)
    setResult(null)
    setErrorMessage('')
  }

  const startImport = async () => {
    if (!file || importing) return
    setErrorMessage('')
    setResult(null)
    setImporting(true)
    try {
      const imported = await importDeviceResource(tab, file)
      setResult(imported)
      if (imported.importedCount + imported.updatedCount > 0) {
        toast.success(formatImportSummary(imported))
        onImported?.()
      } else {
        toast.warning(formatImportSummary(imported))
      }
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? (error.userMessage || error.message) : '导入失败，请稍后重试'
      )
    } finally {
      setImporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导入{label}</DialogTitle>
          <DialogDescription>
            从 JSON / CSV / Excel 文件导入{label}配置，按唯一标识匹配更新或新建
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 拖拽 / 点击选文件（§4.5.1 步骤 3） */}
          <div
            onDragOver={(event) => {
              event.preventDefault()
              if (importing) return
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              if (importing) return
              selectFile(event.dataTransfer.files?.[0])
            }}
            className={cn(
              'border-border/60 hover:bg-muted/30 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-7 text-center transition-colors',
              dragging && 'border-primary bg-primary/[0.04]',
              importing && 'pointer-events-none opacity-60'
            )}
          >
            <UploadCloud aria-hidden='true' className='text-muted-foreground size-8' />
            <p className='text-sm'>
              {file ? (
                <span className='font-medium break-all'>{file.name}</span>
              ) : (
                '点击或拖拽文件到此处上传'
              )}
            </p>
            <p className='text-muted-foreground text-xs'>{DEVICES_IMPORT_FORMAT_HINT}</p>
            <Button
              variant='outline'
              size='sm'
              type='button'
              disabled={importing}
              onClick={() => fileRef.current?.click()}
            >
              <FileUp aria-hidden='true' className='size-3.5' />
              选择文件
            </Button>
            <input
              ref={fileRef}
              type='file'
              accept={DEVICES_IMPORT_ACCEPT}
              className='hidden'
              onChange={(event) => {
                selectFile(event.target.files?.[0])
                event.target.value = ''
              }}
            />
          </div>

          {/* 导入结果（§4.5.1 步骤 5：成功 / 更新 / 跳过计数 + errors 行号） */}
          {result && (
            <div className='space-y-2 rounded-lg border p-3'>
              <p className='flex items-center gap-1.5 text-sm font-medium'>
                <CheckCircle2 aria-hidden='true' className='text-success size-4' />
                {formatImportSummary(result)}
              </p>
              {result.errors.length > 0 && (
                <ScrollArea className='max-h-36 rounded-md border'>
                  <ul className='divide-border divide-y'>
                    {result.errors.map((message, index) => (
                      <li
                        key={`${index}-${message}`}
                        className='text-destructive px-2.5 py-1.5 text-xs break-all'
                      >
                        {message}
                      </li>
                    ))}
                  </ul>
                </ScrollArea>
              )}
              <p className='text-muted-foreground text-xs'>设备状态以本环境为准</p>
            </div>
          )}

          {errorMessage && <p className='text-destructive text-xs'>{errorMessage}</p>}
          {importing && (
            <p className='text-muted-foreground flex items-center gap-2 text-xs'>
              <Spinner size={14} />
              正在导入，请稍候…
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' disabled={importing} onClick={() => handleOpenChange(false)}>
            {result ? '关闭' : '取消'}
          </Button>
          <Button disabled={!file || importing} onClick={() => void startImport()}>
            {importing ? (
              <>
                <Spinner size={14} className='text-current' />
                正在导入…
              </>
            ) : (
              '开始导入'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
