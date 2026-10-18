/**
 * 冻结报告弹窗（09_任务域.md §5.13，Dialog sm:max-w-4xl）。
 * 标题「冻结报告（发布时快照 · 不可变）」+ 头部「查看源报告 #{id}」link（→ /report/{id}）。
 * 内容 = 只读报告视图（报告组件归报告域卡 INT-360，本卡只定壳：报告头/统计行/结论/
 * 冻结用例表）；快照无 summary/cases 时渲染空态「该快照缺少可渲染的冻结报告数据（发布时无报告）」。
 */
import { useMemo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { ExternalLink } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { ReportSnapshot, ReportSnapshotCase } from '@/domain/models/task'
import { readReportSummary } from '@/domain/models/task'

/** 报告状态中文（只读展示；published/草稿 语义随报告域卡统一） */
function statusLabel(status: string | null | undefined): string {
  const map: Record<string, string> = {
    published: '已发布',
    draft: '草稿',
  }
  return (status && map[status]) || status || '—'
}

function StatItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='flex flex-col gap-0.5'>
      <span className='text-muted-foreground text-xs'>{label}</span>
      <span className='text-sm font-medium tabular-nums'>{value ?? '—'}</span>
    </div>
  )
}

function ReportCaseRow({ c }: { c: ReportSnapshotCase }) {
  const metrics = Object.entries(c.metrics ?? {})
  return (
    <div className='hover:bg-muted/40 border-b px-3 py-2 transition-colors'>
      <div className='flex flex-wrap items-center gap-1.5 text-sm'>
        <span className='font-medium'>{c.name || c.testCaseId || `#${c.id ?? '—'}`}</span>
        {c.category && (
          <Badge variant='outline' className='rounded-md px-1.5 text-[11px]'>
            {c.category}
          </Badge>
        )}
        {(c.tags ?? []).length > 0 && (
          <span className='text-muted-foreground text-xs'>{(c.tags ?? []).join('、')}</span>
        )}
      </div>
      {metrics.length > 0 && (
        <div className='text-muted-foreground mt-1 flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-xs tabular-nums'>
          {metrics.map(([key, value]) => (
            <span key={key}>
              {key}: {String(value ?? '—')}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function ReportSnapshotDialog({
  open,
  onOpenChange,
  report,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 报告快照（source = PublishedTaskDetail.report_snapshot；null → 空态） */
  report: ReportSnapshot | null
}) {
  const navigate = useNavigate()

  const sourceReportId = useMemo(
    () => report?.sourceReportId ?? report?.reportId ?? null,
    [report]
  )

  /** 存量快照无 summary/cases 时不可渲染（空态） */
  const hasRenderableData = useMemo(() => {
    if (!report) return false
    return (
      (!!report.summary && Object.keys(report.summary).length > 0) ||
      (report.cases?.length ?? 0) > 0
    )
  }, [report])

  const summary = useMemo(() => readReportSummary(report), [report])

  if (!report) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>冻结报告（发布时快照 · 不可变）</DialogTitle>
          <DialogDescription>快照数据不随源报告修改/删除影响</DialogDescription>
        </DialogHeader>

        {sourceReportId && (
          <div className='flex items-center justify-end'>
            <Button
              size='sm'
              variant='outline'
              className='h-7 gap-1.5'
              onClick={() => void navigate({ to: '/report/$reportId', params: { reportId: String(sourceReportId) } })}
            >
              <ExternalLink aria-hidden='true' className='size-3.5' />
              查看源报告 #{sourceReportId}
            </Button>
          </div>
        )}

        {!hasRenderableData ? (
          <div className='flex flex-col items-center gap-2 rounded-lg border border-dashed bg-muted/30 px-4 py-10 text-sm text-muted-foreground'>
            <p>该快照缺少可渲染的冻结报告数据（发布时无报告）</p>
          </div>
        ) : (
          <ScrollArea className='max-h-[min(72dvh,720px)] pr-1'>
            <div className='flex flex-col gap-3'>
              {/* 报告头（只读） */}
              <div className='rounded-lg border p-3'>
                <div className='flex flex-wrap items-center gap-2'>
                  <span className='text-base font-medium'>{report.name}</span>
                  <StatusBadge label={statusLabel(report.status)} variant='success' />
                  {report.type && (
                    <Badge variant='outline' className='rounded-md px-1.5'>
                      {report.type}
                    </Badge>
                  )}
                </div>
                {report.description && (
                  <p className='text-muted-foreground mt-1 text-xs'>{report.description}</p>
                )}
                <Separator className='my-2.5' />
                <div className='grid grid-cols-2 gap-2 sm:grid-cols-5'>
                  <StatItem label='用例总数' value={summary.caseCount} />
                  <StatItem label='已完成' value={summary.completedCases} />
                  <StatItem label='失败' value={summary.failedCases} />
                  <StatItem label='通过率' value={summary.passRate != null ? `${summary.passRate}%` : null} />
                  <StatItem label='耗时（s）' value={summary.duration} />
                </div>
              </div>

              {/* 结论 */}
              {report.analysis && (
                <div className='rounded-lg border p-3'>
                  <p className='text-sm font-medium'>结论</p>
                  <p className='text-muted-foreground mt-1 whitespace-pre-wrap text-xs leading-5'>
                    {report.analysis}
                  </p>
                </div>
              )}

              {/* 冻结用例表（只读） */}
              <div className='overflow-hidden rounded-lg border'>
                <p className='bg-[var(--table-header)] px-3 py-2 text-xs font-medium'>
                  冻结用例（{(report.cases ?? []).length}）
                </p>
                {(report.cases ?? []).length === 0 ? (
                  <p className='text-muted-foreground px-3 py-4 text-center text-xs'>
                    该快照未冻结用例明细
                  </p>
                ) : (
                  <div className='divide-y divide-border'>
                    {(report.cases ?? []).map((c, idx) => (
                      <ReportCaseRow key={c.id ?? `${c.testCaseId ?? 'case'}-${idx}`} c={c} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </ScrollArea>
        )}
      </DialogContent>
    </Dialog>
  )
}
