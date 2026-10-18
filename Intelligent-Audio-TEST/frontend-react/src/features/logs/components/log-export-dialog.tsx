/**
 * 导出日志 Dialog（features/logs；17_配置运维.md §4.7/§7.9，sm:max-w-lg，log:read）。
 * 当前筛选条件回显（时间范围/分类/模块/级别/标记/算法）+ 格式 Select[文本/JSON/CSV]
 * + 主钮「导出」→ POST /logs/export（后端 FileResponse 原始文件流，下载 txt/json/csv）。
 */
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
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
import { LOG_MARK_OPTIONS, LOG_MODULE_OPTIONS, LOG_CATEGORY_OPTIONS } from '@/domain/models/log'
import type { LogFilterState } from '@/features/logs/types'

const EXPORT_FORMATS = [
  { value: 'txt', label: '文本 (.txt)' },
  { value: 'json', label: 'JSON (.json)' },
  { value: 'csv', label: 'CSV (.csv)' },
] as const

export type LogExportDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  filters: LogFilterState
  selectedLevels: string[]
  pending: boolean
  onExport: (format: string) => void
}

function optionLabel(
  options: readonly { value: string; label: string }[],
  value: string
): string {
  return options.find((option) => option.value === value)?.label ?? '全部'
}

export function LogExportDialog({
  open,
  onOpenChange,
  filters,
  selectedLevels,
  pending,
  onExport,
}: LogExportDialogProps) {
  const [format, setFormat] = useState('txt')

  const conditionParts = [
    filters.startTime || filters.endTime
      ? `时间 ${filters.startTime || '…'} ~ ${filters.endTime || '…'}`
      : '',
    filters.category !== 'all' ? `分类 ${optionLabel(LOG_CATEGORY_OPTIONS, filters.category)}` : '',
    filters.module !== 'all' ? `模块 ${optionLabel(LOG_MODULE_OPTIONS, filters.module)}` : '',
    filters.mark !== 'all' ? `标记 ${optionLabel(LOG_MARK_OPTIONS, filters.mark)}` : '',
    filters.algorithmType !== 'all' ? `算法 ${filters.algorithmType}` : '',
  ].filter(Boolean)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导出日志</DialogTitle>
          <DialogDescription>按当前筛选条件导出日志文件</DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 py-1'>
          <div className='text-muted-foreground flex flex-wrap gap-1 text-xs'>
            {conditionParts.length > 0 ? (
              conditionParts.map((part) => (
                <span key={part} className='border-border/60 bg-muted/30 rounded-md border px-2 py-1'>
                  {part}
                </span>
              ))
            ) : (
              <span>未设置筛选条件（导出全部日志）</span>
            )}
            {selectedLevels.length > 0 && selectedLevels.length < 5 && (
              <span className='border-border/60 bg-muted/30 rounded-md border px-2 py-1'>
                级别 {selectedLevels.join('/')}
              </span>
            )}
          </div>
          <div className='grid items-center gap-2 sm:grid-cols-[auto_1fr]'>
            <span className='text-muted-foreground text-sm'>格式</span>
            <Select value={format} onValueChange={(value) => setFormat(value ?? 'txt')}>
              <SelectTrigger size='sm'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXPORT_FORMATS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant='outline' size='sm'>取消</Button>} />
          <Button size='sm' disabled={pending} onClick={() => onExport(format)}>
            导出
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
