/**
 * 用例详情 Dialog（15_报告域.md §4.7：TestCaseReportDetail 七块全量 + 详细日志）。
 */
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'

import { CaseReportDetail } from '../case-report-detail'

interface CaseDetailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseItem?: ReportCaseItem
  report: ReportDetailData
}

export function CaseDetailDialog({
  open,
  onOpenChange,
  caseItem,
  report,
}: CaseDetailDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>
            {caseItem?.name ?? '用例详情'}
            {caseItem?.id && (
              <span className='text-muted-foreground ms-2 font-mono text-sm'>{caseItem.id}</span>
            )}
          </DialogTitle>
        </DialogHeader>
        <div className='max-h-[70vh] overflow-y-auto pr-1'>
          {caseItem ? (
            <CaseReportDetail caseItem={caseItem} report={report} />
          ) : (
            <p className='text-muted-foreground p-4 text-center text-sm'>暂无用例数据</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
