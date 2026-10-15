/**
 * 分析结论（规范 §4.6，可编辑）：非编辑态 analysis 文本（whitespace-pre-wrap）；
 * 编辑态 Textarea（field-sizing-content min-h-24 max-h-96）+ 保存/取消 → PUT /reports/{id}。
 * AI 自动撰写搁置（§10-4），标题下标注「报告生成后自动撰写，可编辑补充」。
 */
import { Pencil, Save, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { ReportDetailData } from '@/domain/models/report'

interface ReportConclusionProps {
  report: ReportDetailData
  editing: boolean
  onExitEditing: () => void
  onSaveAnalysis: (analysis: string) => void
}

export function ReportConclusion({
  report,
  editing,
  onExitEditing,
  onSaveAnalysis,
}: ReportConclusionProps) {
  const [draft, setDraft] = useState(report.analysis ?? '')
  // 报告切换/进入编辑时同步草稿
  const [lastReportId, setLastReportId] = useState(report.id)
  if (lastReportId !== report.id) {
    setLastReportId(report.id)
    setDraft(report.analysis ?? '')
  }

  const handleSave = () => {
    onSaveAnalysis(draft)
    toast.success('结论保存成功')
  }

  return (
    <div className='space-y-2'>
      <div className='flex flex-wrap items-baseline justify-between gap-2'>
        <h3 className='text-sm font-semibold'>分析结论</h3>
        <span className='text-muted-foreground text-xs'>
          报告生成后自动撰写，可编辑补充
        </span>
      </div>

      {editing ? (
        <div className='space-y-2'>
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder='请输入分析结论...'
            className='field-sizing-content min-h-24 max-h-96'
          />
          <div className='flex items-center gap-2'>
            <Button size='sm' onClick={handleSave}>
              <Save data-icon='inline-start' />
              保存
            </Button>
            <Button variant='outline' size='sm' onClick={onExitEditing}>
              <X data-icon='inline-start' />
              取消
            </Button>
          </div>
        </div>
      ) : report.analysis ? (
        <p className='text-muted-foreground text-sm leading-7 whitespace-pre-wrap'>
          {report.analysis}
        </p>
      ) : (
        <div className='text-muted-foreground flex items-center gap-2 rounded-lg border border-dashed px-3 py-6 text-sm'>
          <Pencil className='size-4' aria-hidden='true' />
          暂无分析结论
        </div>
      )}
    </div>
  )
}
