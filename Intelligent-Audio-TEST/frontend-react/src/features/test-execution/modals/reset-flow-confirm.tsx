/**
 * 重置流程确认（§5.5；interfaces/features/test-execution/modals）。
 * ConfirmDialog destructive：「将清空当前流程的所有选择与进度，是否继续？」主钮「重置」。
 * 步骤四「开始新测试」确认（§3.8）：「将开始新的测试流程，当前报告不受影响。是否继续？」
 * 5.6 停止 / 5.7 移除用例走共用 ConfirmDialog 配置（INT-354 §5.8/§5.9 组件同源引用）。
 */
import { ConfirmDialog } from '@/components/confirm-dialog'

interface ResetFlowConfirmProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function ResetFlowConfirm({ open, onOpenChange, onConfirm }: ResetFlowConfirmProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title='重置流程'
      desc='将清空当前流程的所有选择与进度，是否继续？'
      confirmText='重置'
      destructive
      handleConfirm={onConfirm}
    />
  )
}
