/**
 * 报表生成表单（15_报告域.md §2.2「报表生成」页签 + §4.4 流程：报表类型/格式/执行）。
 * 报表类型 Select × 报表格式 Select +「生成报表」执行按钮；导出链路复用
 * application/use-statistics-export（POST /reports/export，只接受 ids + format）。
 * INT-1905 P3-1：原「报表内容」Checkbox 组为死控件（导出链路无内容项参数，勾选不改变结果），
 * 后端 report_service 补齐内容项契约前先行移除，不留无效交互（见交付评论的 FEAT 缺口）。
 */
import { FileOutput } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useStatisticsExport } from '@/application/report-statistics/use-statistics-export'
import {
  REPORT_FORM_FORMATS,
  REPORT_FORM_TYPES,
} from '@/features/report-statistics/constants'

export function StatisticsReportForm({ reportIds }: { reportIds: number[] }) {
  const [reportType, setReportType] = useState<string>(REPORT_FORM_TYPES[0])
  const [format, setFormat] = useState('excel')
  const [title, setTitle] = useState('')
  const { exportStatistics, exporting } = useStatisticsExport()

  const handleRun = () => {
    void exportStatistics({
      format: format as 'excel' | 'csv' | 'pdf' | 'html',
      name: title || reportType,
      ids: reportIds,
    })
  }

  return (
    <div className='bg-card rounded-2xl border shadow-xs p-4 sm:p-5'>
      <h4 className='text-sm font-semibold'>报表生成</h4>
      <div className='mt-4 grid gap-4 sm:grid-cols-2'>
        <div className='flex flex-col gap-1.5'>
          <label htmlFor='report-type' className='text-muted-foreground text-xs font-medium'>
            报表类型
          </label>
          <Select value={reportType} onValueChange={(v) => setReportType(v ?? REPORT_FORM_TYPES[0])}>
            <SelectTrigger id='report-type' className='h-9'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent align='start'>
              {REPORT_FORM_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className='flex flex-col gap-1.5'>
          <label htmlFor='report-format' className='text-muted-foreground text-xs font-medium'>
            报表格式
          </label>
          <Select value={format} onValueChange={(v) => setFormat(v ?? 'excel')}>
            <SelectTrigger id='report-format' className='h-9'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent align='start'>
              {REPORT_FORM_FORMATS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className='flex flex-col gap-1.5 sm:col-span-2'>
          <label htmlFor='report-title' className='text-muted-foreground text-xs font-medium'>
            报表名称
          </label>
          <Input
            id='report-title'
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder='请输入报表名称'
            className='h-9'
          />
        </div>
      </div>

      <div className='mt-4 flex justify-end'>
        <Button size='sm' className='h-9 font-medium' disabled={exporting} onClick={handleRun}>
          <FileOutput data-icon='inline-start' />
          {exporting ? '生成中...' : '生成报表'}
        </Button>
      </div>
    </div>
  )
}
