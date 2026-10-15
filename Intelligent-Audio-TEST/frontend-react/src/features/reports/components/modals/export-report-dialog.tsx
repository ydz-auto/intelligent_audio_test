/**
 * 导出报告 Dialog（规范 §4.9/§5.3，report:read）：范围回显（单/批量）+ 格式 Select
 * [CSV·Excel·PDF·HTML] + 说明 + 主钮「导出」（POST /reports/export，zip_base64→Blob）。
 */
import { Download } from 'lucide-react'
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
import { Badge } from '@/components/ui/badge'

const EXPORT_FORMATS = [
  { value: 'csv', label: 'CSV（批量摘要）' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML（所见即所得）' },
] as const

interface ExportReportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 导出范围描述（单报告名 / 已选择 {n} 个报告） */
  scope: string
  count: number
  onExport: (format: string) => void
}

export function ExportReportDialog({
  open,
  onOpenChange,
  scope,
  count,
  onExport,
}: ExportReportDialogProps) {
  const [format, setFormat] = useState<string>('csv')
  const [exporting, setExporting] = useState(false)

  const handleExport = async () => {
    setExporting(true)
    try {
      await onExport(format)
    } finally {
      setExporting(false)
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导出报告</DialogTitle>
          <DialogDescription>
            导出内容为报告落库数据的快照，由后端统一生成，前端不做二次计算。
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='flex items-center gap-2'>
            <Badge variant='secondary'>{count} 个报告</Badge>
            <span className='text-muted-foreground truncate text-sm'>{scope}</span>
          </div>
          <div className='space-y-2'>
            <span className='text-sm font-medium'>格式</span>
            <Select value={format} onValueChange={(value) => setFormat(value ?? 'csv')}>
              <SelectTrigger className='w-full justify-between'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXPORT_FORMATS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={exporting} onClick={() => void handleExport()}>
            <Download data-icon='inline-start' />
            {exporting ? '导出中...' : '导出'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
