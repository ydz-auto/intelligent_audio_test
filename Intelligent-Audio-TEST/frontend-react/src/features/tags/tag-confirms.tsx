/**
 * 标签管理页删除确认族（11_用例域.md §4.2/§5.4，ConfirmDialog + destructive）。
 * 标签删除=软删不级联（默认语义「确定删除标签「{名}」吗？」）；
 * 分类删除拦截在调用侧（tagCount>0 禁用+Tooltip），空分类才走到本确认。
 */
import { ConfirmDialog } from '@/components/confirm-dialog'

export type TagConfirmKind = 'delete-tag' | 'delete-category'

export interface TagConfirmState {
  kind: TagConfirmKind
  name: string
  /** 分类 id（删除分类后选中态回退未分类判定用） */
  id?: number
}

/** 确认文案构建（§4.2/§8 逐字） */
export function buildTagConfirmCopy(
  kind: TagConfirmKind,
  name: string
): { title: string; desc: string; confirmText: string; destructive: boolean } {
  if (kind === 'delete-category') {
    return {
      title: '删除分类',
      desc: `确定删除分类「${name}」吗？此操作不可恢复。`,
      confirmText: '删除',
      destructive: true,
    }
  }
  return {
    title: '删除标签',
    desc: `确定删除标签「${name}」吗？`,
    confirmText: '删除',
    destructive: true,
  }
}

/** 通用确认弹窗（页面级状态驱动；文案经 buildTagConfirmCopy 构建） */
export function TagConfirmDialog({
  open,
  onOpenChange,
  state,
  onConfirm,
  pending = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  state: TagConfirmState | null
  onConfirm: (state: TagConfirmState) => void
  /** 请求进行中禁用确认钮（真实 DELETE 接线后防重复提交） */
  pending?: boolean
}) {
  if (!state) return null
  const copy = buildTagConfirmCopy(state.kind, state.name)
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={copy.title}
      desc={copy.desc}
      confirmText={copy.confirmText}
      destructive={copy.destructive}
      isLoading={pending}
      handleConfirm={() => onConfirm(state)}
    />
  )
}
