/**
 * 导出日志弹窗（interfaces 层；17_配置运维.md §7.9，Dialog sm:max-w-lg，log:read）。
 * 当前筛选条件摘要回显（时间范围/分类/模块/级别/标记/算法）+ 格式 Select[文本/JSON/CSV]
 * + 主钮「导出」→ POST /logs/export（Blob 下载，见 useLogMutations.exportLogs）。
 */
import { useState } from 'react'

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
import type { LogExportInput } from '@/domain/models/log'
import { LOG_EXPORT_FORMATS } from '@/features/logs/constants'

export type LogFilterSummary = {
  startTime?: string
  endTime?: string
  category?: string
  module?: string
  level?: string
  mark?: string
  algorithmType?: string
  keyword?: string
}

export type ExportLogsDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  summary: LogFilterSummary
  onExport: (format: LogExportInput['format']) => void
  isPending: boolean
}

function renderSummaryItem(label: string, value: string | undefined) {
  return (
    <div className='flex items-baseline gap-2 text-xs'>
      <span className='text-muted-foreground w-16 shrink-0'>{label}</span>
      <span className='min-w-0 truncate font-mono'>{value || '全部'}</span>
    </div>
  )
}

export function ExportLogsDialog(props: ExportLogsDialogProps) {
  const [format, setFormat] = useState<LogExportInput['format']>('txt')
  const { summary } = props

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导出日志</DialogTitle>
          <DialogDescription>按当前筛选条件导出日志文件。</DialogDescription>
        </DialogHeader>

        <div className='bg-muted/30 grid gap-1.5 rounded-lg border p-3'>
          <div className='text-muted-foreground mb-0.5 text-xs font-medium'>
            当前筛选条件
          </div>
          {renderSummaryItem('时间范围', summary.startTime ? `${summary.startTime} 至 ${summary.endTime ?? '现在'}` : undefined)}
          {renderSummaryItem('分类', summary.category)}
          {renderSummaryItem('模块', summary.module)}
          {renderSummaryItem('级别', summary.level)}
          {renderSummaryItem('标记', summary.mark)}
          {renderSummaryItem('算法', summary.algorithmType)}
          {renderSummaryItem('关键词', summary.keyword)}
        </div>

        <div className='flex items-center gap-2'>
          <label htmlFor='log-export-format' className='text-muted-foreground text-sm'>
            格式
          </label>
          <Select value={format} onValueChange={(v) => setFormat((v ?? 'txt') as LogExportInput['format'])}>
            <SelectTrigger id='log-export-format' className='w-36' size='sm'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOG_EXPORT_FORMATS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            size='sm'
            onClick={() => props.onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            size='sm'
            disabled={props.isPending}
            onClick={() => props.onExport(format)}
          >
            {props.isPending ? '导出中…' : '导出'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
