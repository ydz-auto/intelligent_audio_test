/**
 * 分组/标签组头操作面板（V9.7.10 TestCaseGroupActions.vue 等价移植，11_用例域.md §3.5）。
 * 组头按钮：编辑分组 / 删除分组 / 新增用例到此分组 / 复制分组 + 「批量修改」下拉九项
 * （用例专属参数/播放设备/声压/调整分组/评价维度/噪声/标签生成名称/管理标签/用例参考更新，
 * 与 §3.7 批量浮条同源载荷，两通道同源）。
 * 批量九项触发 onBatchAction(action, ids)——ids=组内已勾选否则组内全量（resolveCaseIds 语义）。
 * 组内用例懒加载（分组收起时 caseIds 为空），空 ids 由 useCaseBatchActions.openBatch 统一拦截
 * 并提示「请先展开分组或勾选用例」（INT-1780，不再按 0 条提交并提示成功）。
 * 末项「删除用例」走 onBatchAction('delete') → 批量删除确认 → 真实 POST /testcases/batch（INT-1780）。
 * 回收站态整组操作面板隐藏（INT-215 口径：trashMode 下组头无批量/编辑/删除）。
 */
import { ChevronDown, Copy, Pencil, Plus, Settings2, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { BatchActionKey } from '@/features/testcases/components/case-bulk-actions'
import type {
  SubViewOption,
  SubViewValue,
} from '@/features/testcases/components/case-sub-view-toggle'

/** 批量修改九项（对齐 V9.7.10 TestCaseGroupActions.vue 逐字文案） */
export const GROUP_BATCH_ITEMS: Array<{ key: BatchActionKey; label: string }> = [
  { key: 'params', label: '用例专属参数' },
  { key: 'device', label: '播放设备' },
  { key: 'spl', label: '声压' },
  { key: 'group', label: '调整分组' },
  { key: 'dimensions', label: '评价维度' },
  { key: 'noise', label: '噪声' },
  { key: 'name', label: '标签生成名称' },
  { key: 'tags', label: '管理标签' },
  { key: 'refresh', label: '用例参考更新' },
]

export interface CaseGroupActionsProps {
  /** 组名/标签名（批量九项 toast 回显用） */
  name: string
  /** 组内用例 ID 全量（批量 resolveCaseIds 兜底） */
  caseIds: string[]
  /** 组内已勾选 ID（有勾选用勾选，否则用全量） */
  selectedIds: string[]
  trash: boolean
  onEditGroup?: () => void
  onDeleteGroup?: () => void
  onCreateInGroup?: () => void
  onCopyGroup?: () => void
  onBatchAction?: (action: BatchActionKey, ids: string[]) => void
  /** 移动端（≤640px）子视图切换收编（§3.5：下拉首项「显示方式」两子项；传入=渲染） */
  subViewMenu?: {
    value: SubViewValue
    onValueChange: (value: SubViewValue) => void
    options: SubViewOption[]
  }
}

export function CaseGroupActions({
  name,
  caseIds,
  selectedIds,
  trash,
  onEditGroup,
  onDeleteGroup,
  onCreateInGroup,
  onCopyGroup,
  onBatchAction,
  subViewMenu,
}: CaseGroupActionsProps) {
  const [open, setOpen] = useState(false)
  if (trash) return null

  const resolveIds = () => (selectedIds.length > 0 ? selectedIds : caseIds)

  const btn = (
    label: string,
    icon: React.ReactNode,
    onClick: () => void,
    variant: 'secondary' | 'primary' | 'danger' | 'info' = 'secondary'
  ) => (
    <Button
      key={label}
      type='button'
      size='sm'
      className='h-7 gap-1'
      variant={variant === 'primary' ? 'default' : variant === 'danger' ? 'destructive' : variant === 'info' ? 'outline' : 'secondary'}
      onClick={onClick}
    >
      {icon}
      {label}
    </Button>
  )

  return (
    <div className='flex shrink-0 flex-wrap items-center gap-1.5' onClick={(e) => e.stopPropagation()}>
      {onEditGroup && btn('编辑', <Pencil aria-hidden='true' className='size-3.5' />, onEditGroup)}
      {onDeleteGroup && btn('删除', <Trash2 aria-hidden='true' className='size-3.5' />, onDeleteGroup, 'danger')}
      {onCreateInGroup && btn('新增用例', <Plus aria-hidden='true' className='size-3.5' />, onCreateInGroup, 'primary')}
      {onCopyGroup && btn('复制', <Copy aria-hidden='true' className='size-3.5' />, onCopyGroup, 'info')}
      {onBatchAction && (
        <DropdownMenu open={open} onOpenChange={setOpen}>
          <DropdownMenuTrigger
            render={
              <Button
                type='button'
                size='sm'
                className='h-7 gap-1'
                variant='outline'
                aria-label={`${name} 批量修改`}
              />
            }
          >
            <Settings2 aria-hidden='true' className='size-3.5' />
            批量修改
            <ChevronDown
              aria-hidden='true'
              className={open ? 'size-3.5 rotate-180 transition-transform' : 'size-3.5 transition-transform'}
            />
          </DropdownMenuTrigger>
          <DropdownMenuContent align='end' className='w-44'>
            <DropdownMenuGroup>
              <DropdownMenuLabel className='truncate'>批量修改 · {name}</DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            {subViewMenu && (
              <>
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>显示方式</DropdownMenuSubTrigger>
                  <DropdownMenuSubContent alignOffset={-3}>
                    {subViewMenu.options.map((o) => (
                      <DropdownMenuItem
                        key={o.key}
                        onSelect={() => {
                          subViewMenu.onValueChange(o.key)
                          setOpen(false)
                        }}
                      >
                        {o.label}
                        {subViewMenu.value === o.key && (
                          <span className='ms-auto font-medium'>✓</span>
                        )}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
                <DropdownMenuSeparator />
              </>
            )}
            {GROUP_BATCH_ITEMS.map((item) => (
              <DropdownMenuItem
                key={item.key}
                onSelect={() => {
                  onBatchAction(item.key, resolveIds())
                  setOpen(false)
                }}
              >
                {item.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            {/* INT-1780：原实现只 toast.success('批量删除用例')、不发任何请求（假成功）。
                改走 onBatchAction('delete') → 批量删除确认弹窗 → 真实 POST /testcases/batch（delete）。
                V9.7.10 组头菜单无此项（React 侧新增），保留入口但必须真实生效。 */}
            <DropdownMenuItem
              data-variant='destructive'
              onSelect={() => {
                onBatchAction('delete', resolveIds())
                setOpen(false)
              }}
            >
              删除用例
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  )
}
