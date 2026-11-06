/**
 * 算法确认弹窗族（§7.4/7.5/7.7/7.8；ConfirmDialog 对位，destructive 主钮 + isLoading）。
 * 复制（default）/ 删除算法（destructive）/ 重载配置（default）/ 批量删除（destructive）。
 */
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import type {
  AlgorithmConfirmState,
} from '@/features/algorithm-config/types'

export type AlgorithmConfirmDialogsProps = {
  state: AlgorithmConfirmState
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  pending: boolean
}

export function AlgorithmConfirmDialogs(props: AlgorithmConfirmDialogsProps) {
  const state = props.state
  const open = state != null

  let title = '确认操作'
  let description = ''
  let confirmLabel = '确认'
  let destructive = false

  if (state?.kind === 'clone') {
    title = '确认复制'
    description = `确定要复制算法「${state.algorithm.name}」吗？副本将命名为「${state.algorithm.name} (副本)」并复制全部参数与映射。`
    confirmLabel = '复制'
  } else if (state?.kind === 'delete') {
    title = '确认删除'
    description = `确定要删除算法「${state.algorithm.name}」吗？此操作不可恢复。若算法已被测试任务或用例引用将无法删除。`
    confirmLabel = '删除'
    destructive = true
  } else if (state?.kind === 'reload') {
    title = '重载配置'
    description = '将重载后端算法配置缓存，使最近变更立即生效。确定重载吗？'
    confirmLabel = '重载'
  } else if (state?.kind === 'bulk-delete') {
    title = '批量删除'
    description = `将删除已选择的 ${state.count} 个算法。此操作不可恢复。`
    confirmLabel = '删除'
    destructive = true
  }

  return (
    <AlertDialog open={open} onOpenChange={props.onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={props.pending}>取消</AlertDialogCancel>
          <AlertDialogAction
            variant={destructive ? 'destructive' : 'default'}
            disabled={props.pending}
            onClick={props.onConfirm}
          >
            {props.pending ? '处理中…' : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
