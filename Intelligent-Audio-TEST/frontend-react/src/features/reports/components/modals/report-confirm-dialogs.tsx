/**
 * 报告确认类 Dialog（规范 §5.2/§5.4/§5.8）：发布/删除（软删进回收站）/彻底删除/重新生成，
 * 全部走 ConfirmDialog（AlertDialog + destructive 语义），文案为 §8 定稿中文。
 * target 仅消费 id/name，列表项与详情均可传入。
 */
import { ConfirmDialog } from '@/components/confirm-dialog'

export interface ReportDialogTarget {
  id: number
  name: string
}

export interface SingleReportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  report?: ReportDialogTarget
  onConfirm: (report: ReportDialogTarget) => void
  isLoading?: boolean
}

export function PublishReportDialog({
  open,
  onOpenChange,
  report,
  onConfirm,
  isLoading,
}: SingleReportDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title='发布报告'
      desc='确定要发布该报告吗？发布后状态变为已发布。'
      confirmText='发布'
      handleConfirm={() => report && onConfirm(report)}
      isLoading={isLoading}
    />
  )
}

export function DeleteReportDialog({
  open,
  onOpenChange,
  report,
  onConfirm,
  isLoading,
}: SingleReportDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title='删除报告'
      desc={`将把报告「${report?.name ?? ''}」移入回收站，可在回收站恢复。`}
      confirmText='删除'
      destructive
      handleConfirm={() => report && onConfirm(report)}
      isLoading={isLoading}
    />
  )
}

export function PurgeReportDialog({
  open,
  onOpenChange,
  report,
  onConfirm,
  isLoading,
}: SingleReportDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title='彻底删除'
      desc={`将永久删除报告「${report?.name ?? ''}」及其全部报告数据，此操作不可恢复。`}
      confirmText='彻底删除'
      destructive
      handleConfirm={() => report && onConfirm(report)}
      isLoading={isLoading}
    />
  )
}

export function RegenerateReportDialog({
  open,
  onOpenChange,
  report,
  onConfirm,
  isLoading,
}: SingleReportDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title='重新生成报告'
      desc='将重新计算并覆盖当前报告数据，确定重新生成吗？'
      confirmText='重新生成'
      handleConfirm={() => report && onConfirm(report)}
      isLoading={isLoading}
    />
  )
}

/** 批量删除（软删）/ 批量彻底删除（ConfirmDialog 文案按 §8） */
export function BatchConfirmDialog(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  desc: string
  confirmText?: string
  destructive?: boolean
  isLoading?: boolean
  onConfirm: () => void
}) {
  return (
    <ConfirmDialog
      open={props.open}
      onOpenChange={props.onOpenChange}
      title={props.title}
      desc={props.desc}
      confirmText={props.confirmText}
      destructive={props.destructive}
      handleConfirm={props.onConfirm}
      isLoading={props.isLoading}
    />
  )
}
