/**
 * 报告头（规范 §4.2，对位 newAPI pricing ModelHeader）：
 * 标题(font-mono) + CopyButton + 类型/状态徽标 + 任务信息 + 算法徽标 + 时间 + 描述 + 操作组。
 * 只读快照语义：报告算法为快照值，不随全局切换联动（§2.2）。
 */
import {
  ArrowLeft,
  ExternalLink,
  FileDown,
  Pencil,
  Printer,
  RefreshCw,
  Rocket,
  X,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/copy-button'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { ReportDetailData } from '@/domain/models/report'

import {
  formatDateTime,
  getAlgorithmLabel,
  REPORT_STATUS_META,
  REPORT_TYPE_META,
} from '@/features/reports/constants'

interface ReportHeaderProps {
  report: ReportDetailData
  hasPermission: (permission: string) => boolean
  editing: boolean
  /** 返回按钮文案（回退来源入口：管理页进→报告中心，展示页进→报告展示） */
  backLabel: string
  onBack: () => void
  onEdit: () => void
  onSave: () => void
  onPublish: () => void
  onUnpublish: () => void
  onExport: () => void
  onRegenerate: () => void
  onCopyLink: () => void
  onClose: () => void
}

export function ReportHeader({
  report,
  hasPermission,
  editing,
  backLabel,
  onBack,
  onEdit,
  onSave,
  onPublish,
  onUnpublish,
  onExport,
  onRegenerate,
  onCopyLink,
  onClose,
}: ReportHeaderProps) {
  const typeMeta = REPORT_TYPE_META[report.type]
  const statusMeta = REPORT_STATUS_META[report.status]
  const isComparison =
    report.type === 'comparison' || report.type === 'secondary_comparison'

  return (
    <div className='space-y-4'>
      <Button variant='ghost' size='sm' onClick={onBack} className='-ml-2'>
        <ArrowLeft data-icon='inline-start' />
        {backLabel}
      </Button>

      <div className='bg-card from-primary/5 via-transparent to-transparent rounded-2xl border bg-gradient-to-br p-5 sm:p-6'>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div className='min-w-0 flex-1'>
            <div className='flex flex-wrap items-center gap-2'>
              <h1 className='font-mono max-w-full text-2xl leading-tight font-bold tracking-tight break-all'>
                {report.name}
              </h1>
              <CopyButton value={report.name} aria-label='复制报告名称' />
            </div>
            <div className='mt-2 flex flex-wrap items-center gap-2 text-sm'>
              <StatusBadge label={typeMeta.label} variant={typeMeta.variant} />
              <StatusBadge label={statusMeta.label} variant={statusMeta.variant} />
              {report.algorithm_type && (
                <Badge variant='secondary'>
                  算法：{getAlgorithmLabel(report.algorithm_type)}
                </Badge>
              )}
            </div>
            <div className='text-muted-foreground mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs'>
              {isComparison ? (
                <span>{report.summary.task_count ?? report.summary.resources.length} 个任务对比</span>
              ) : (
                <span className='flex items-center gap-1'>
                  任务：{report.task_name}
                  <span className='font-mono'>#{report.task_id ?? ''}</span>
                </span>
              )}
              <span className='font-mono tabular-nums'>
                创建于 {formatDateTime(report.created_at)}
              </span>
              {report.updated_at && (
                <span className='font-mono tabular-nums'>
                  更新于 {formatDateTime(report.updated_at)}
                </span>
              )}
            </div>
            {report.description && (
              <p className='text-muted-foreground mt-3 text-sm leading-relaxed'>
                {report.description}
              </p>
            )}
          </div>

          <div className='flex flex-wrap items-center gap-2'>
            {hasPermission('report:update') && (
              <Button
                variant='outline'
                size='sm'
                onClick={onEdit}
                aria-pressed={editing}
              >
                <Pencil data-icon='inline-start' />
                {editing ? '退出编辑' : '编辑'}
              </Button>
            )}
            {editing && hasPermission('report:update') && (
              <Button variant='secondary' size='sm' onClick={onSave}>
                <Rocket data-icon='inline-start' />
                保存
              </Button>
            )}
            {hasPermission('report:publish') && report.status === 'draft' && (
              <Button variant='secondary' size='sm' onClick={onPublish}>
                <Rocket data-icon='inline-start' />
                发布
              </Button>
            )}
            {hasPermission('report:publish') && report.status === 'published' && (
              <Button variant='outline' size='sm' onClick={onUnpublish}>
                取消发布
              </Button>
            )}
            {hasPermission('report:create') && (
              <Button variant='outline' size='sm' onClick={onRegenerate}>
                <RefreshCw data-icon='inline-start' />
                重新生成
              </Button>
            )}
            <Button variant='outline' size='sm' onClick={onExport}>
              <FileDown data-icon='inline-start' />
              导出
            </Button>
            <Button variant='ghost' size='sm' onClick={() => window.print()}>
              <Printer data-icon='inline-start' />
              打印
            </Button>
            <Button variant='ghost' size='sm' onClick={onCopyLink}>
              <ExternalLink data-icon='inline-start' />
              复制链接
            </Button>
            <Button variant='ghost' size='sm' onClick={onClose}>
              <X data-icon='inline-start' />
              关闭
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
