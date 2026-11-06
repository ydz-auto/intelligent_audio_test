/**
 * 用例域确认族（11_用例域.md §5.6 文案逐字 + §3.7 批量复制/恢复 ConfirmDialog 直执行）。
 * 统一 ConfirmDialog（AlertDialog + destructive）壳；危险确认主钮 destructive。
 */
import { ConfirmDialog } from '@/components/confirm-dialog'

export type CaseConfirmKind =
  | 'delete'
  | 'purge'
  | 'restore'
  | 'delete-group'
  | 'restore-all'
  | 'batch-copy'
  | 'batch-delete'
  | 'batch-restore'
  | 'batch-purge'
  | 'auto-name'
  | 'refresh'

export interface CaseConfirmState {
  kind: CaseConfirmKind
  /** 用例名 / 分组名 */
  name?: string
  count?: number
  /** 批量确认的用例 id 集（INT-1026：auto-name/refresh 用弹窗打开时捕获的 ids，
   *  组头「批量修改」无勾选时也正确作用于组内全量——resolveCaseIds 语义） */
  ids?: string[]
}

/** 确认文案构建（§5.6 逐字；用例名引号/书名号口径保留现实现） */
export function buildCaseConfirmCopy(
  kind: CaseConfirmKind,
  name?: string,
  count?: number
): { title: string; desc: string; confirmText: string; destructive?: boolean } {
  switch (kind) {
    case 'delete':
      return {
        title: '删除测试用例',
        desc: `确定要删除测试用例 "${name ?? ''}" 吗？用例将移入回收站，可在回收站恢复。`,
        confirmText: '删除',
        destructive: true,
      }
    case 'purge':
      return {
        title: '彻底删除测试用例',
        desc: `彻底删除用例「${name ?? ''}」？该操作不可恢复（仅管理员/所有者可执行）。`,
        confirmText: '彻底删除',
        destructive: true,
      }
    case 'restore':
      return {
        title: '恢复测试用例',
        desc: `恢复用例「${name ?? ''}」？恢复后将回到正常列表。`,
        confirmText: '恢复',
      }
    case 'delete-group':
      return {
        title: '删除分组',
        desc: `确定要删除分组 "${name ?? ''}" 及其下所有测试用例吗？此操作不可逆！`,
        confirmText: '删除',
        destructive: true,
      }
    case 'restore-all':
      return {
        title: '恢复回收站全部用例',
        desc: `恢复回收站中的全部 ${count ?? 0} 个用例？`,
        confirmText: '全部恢复',
      }
    case 'batch-copy':
      return {
        title: '批量复制用例',
        desc: `确定要复制选中的 ${count ?? 0} 个用例吗？复制后沿用原分组（同名追加 _copy）。`,
        confirmText: '批量复制',
      }
    case 'batch-delete':
      return {
        title: '批量删除用例',
        desc: `确定要删除选中的 ${count ?? 0} 个用例吗？用例将移入回收站。`,
        confirmText: '批量删除',
        destructive: true,
      }
    case 'batch-restore':
      return {
        title: '批量恢复用例',
        desc: `确定要恢复选中的 ${count ?? 0} 个用例吗？`,
        confirmText: '批量恢复',
      }
    case 'batch-purge':
      return {
        title: '批量彻底删除用例',
        desc: `确定要彻底删除选中的 ${count ?? 0} 个用例吗？该操作不可恢复。`,
        confirmText: '批量彻底删除',
        destructive: true,
      }
    case 'auto-name':
      return {
        title: '自动生成名称',
        desc: `将对 ${count ?? 0} 个用例自动生成名称（按标签长度排序，用"-"连接）。是否继续？`,
        confirmText: '确定',
      }
    case 'refresh':
      return {
        title: '刷新参考参数',
        desc: `将对 ${count ?? 0} 个用例刷新参考参数，是否继续？`,
        confirmText: '确定',
      }
  }
}

/** 通用确认弹窗（页面级状态驱动；文案经 buildCaseConfirmCopy 构建） */
export function CaseConfirmDialog({
  open,
  onOpenChange,
  state,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  state: CaseConfirmState | null
  onConfirm: (state: CaseConfirmState) => void
}) {
  if (!state) return null
  const copy = buildCaseConfirmCopy(state.kind, state.name, state.count)
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={copy.title}
      desc={copy.desc}
      confirmText={copy.confirmText}
      destructive={copy.destructive}
      handleConfirm={() => onConfirm(state)}
    />
  )
}
