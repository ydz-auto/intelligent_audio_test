/**
 * 评估维度页确认弹窗族（features/evaluation/modals；11_用例域.md §4.1/§5.6，
 * ConfirmDialog + destructive 文案逐字）。
 * 删除维度 / 批量启用·禁用·删除 / 删除分类 / 复制维度。
 */
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { EvaluationConfirmState } from '@/features/evaluation/types'

/** 确认文案构建（§4.1/§5.6 逐字） */
export function buildConfirmCopy(
  state: EvaluationConfirmState
): {
  title: string
  desc: string
  confirmText: string
  destructive: boolean
} {
  switch (state.kind) {
    case 'delete-dimension':
      return {
        title: '删除维度',
        desc: `确定要删除维度「${state.dimension.name}」吗？此操作不可恢复。`,
        confirmText: '删除',
        destructive: true,
      }
    case 'batch-action': {
      const { action, count } = state
      if (action === 'delete')
        return {
          title: '批量删除',
          desc: `确定要删除选中的 ${count} 个维度吗？`,
          confirmText: '批量删除',
          destructive: true,
        }
      return {
        title: action === 'enable' ? '批量启用' : '批量禁用',
        desc: `确定要${action === 'enable' ? '启用' : '禁用'}选中的 ${count} 个维度吗？`,
        confirmText: action === 'enable' ? '批量启用' : '批量禁用',
        destructive: false,
      }
    }
    case 'delete-category':
      return {
        title: '删除分类',
        desc: `确定删除分类「${state.category.name}」吗？此操作不可恢复。`,
        confirmText: '删除',
        destructive: true,
      }
    case 'duplicate-dimension':
      return {
        title: '复制维度',
        desc: `确定要复制维度「${state.dimension.name}」吗？复制后将深拷贝其 API 配置、权重与关联算法为新维度。`,
        confirmText: '复制',
        destructive: false,
      }
  }
}

export function EvaluationConfirmDialog({
  open,
  onOpenChange,
  state,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  state: EvaluationConfirmState | null
  onConfirm: () => void
}) {
  if (!state) return null
  const copy = buildConfirmCopy(state)
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={copy.title}
      desc={copy.desc}
      confirmText={copy.confirmText}
      destructive={copy.destructive}
      handleConfirm={onConfirm}
    />
  )
}
