/**
 * 用例行操作菜单（11_用例域.md §3.3.2 DataTableRowActionMenu）。
 * 菜单项：预览音频（testcase:preview，无音频配置置灰+Tooltip）/编辑（testcase:update）/
 * 复制用例（testcase:copy）/参考参数（testcase:update）/收藏/取消收藏（testcase:read）/
 * 恢复（testcase:delete，仅回收站态）/彻底删除（testcase:delete，仅回收站态 destructive）/
 * 删除（testcase:delete，回收站态隐藏）。
 * mock 态：动作触发页面级弹窗/toast 演示（接线后替换为 application/testcases mutations）。
 */
import { MoreHorizontal, Star } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { TestCaseListItem } from '@/domain/models/testCase'

type MenuItem = {
  key: string
  label: string
  permission?: string
  destructive?: boolean
  disabled?: boolean
  disabledReason?: string
  onSelect?: () => void
}

export function CaseRowActions({
  caseItem,
  onPreview,
  onEdit,
  onReferenceParams,
  onDelete,
  onRestore,
  onPurge,
}: {
  caseItem: TestCaseListItem
  onPreview: (caseItem: TestCaseListItem) => void
  onEdit: (caseItem: TestCaseListItem) => void
  onReferenceParams: (caseItem: TestCaseListItem) => void
  onDelete: (caseItem: TestCaseListItem) => void
  onRestore: (caseItem: TestCaseListItem) => void
  onPurge: (caseItem: TestCaseListItem) => void
}) {
  const { hasPermission } = usePermissions()
  const [isControlling, setIsControlling] = useState(false)

  const isTrash = caseItem.deleted === true
  // mock：无音频配置判定（id 尾部非偶数为有音频，演示置灰态）
  const hasAudio = !caseItem.id.endsWith('4')
  const items: MenuItem[] = []

  if (hasPermission('testcase:preview')) {
    items.push({
      key: 'preview',
      label: '预览音频',
      disabled: !hasAudio,
      disabledReason: hasAudio ? undefined : '该用例没有关联音频文件',
      onSelect: () => onPreview(caseItem),
    })
  }
  if (hasPermission('testcase:update') && !isTrash) {
    items.push({
      key: 'edit',
      label: '编辑',
      onSelect: () => onEdit(caseItem),
    })
  }
  if (hasPermission('testcase:copy') && !isTrash) {
    items.push({
      key: 'copy',
      label: '复制用例',
      onSelect: () => toastCase('已复制测试用例', `已创建副本：${caseItem.name}_copy`),
    })
  }
  if (hasPermission('testcase:update') && !isTrash) {
    items.push({
      key: 'reference-params',
      label: '参考参数',
      onSelect: () => onReferenceParams(caseItem),
    })
  }
  if (hasPermission('testcase:read')) {
    items.push({
      key: 'favorite',
      label: caseItem.isFavorite ? '取消收藏' : '收藏',
      onSelect: () => toastCase(caseItem.isFavorite ? '已取消收藏' : '已加入收藏'),
    })
  }

  if (isTrash) {
    if (hasPermission('testcase:delete')) {
      items.push(
        {
          key: 'restore',
          label: '恢复',
          onSelect: () => onRestore(caseItem),
        },
        {
          key: 'purge',
          label: '彻底删除',
          destructive: true,
          onSelect: () => onPurge(caseItem),
        }
      )
    }
  } else if (hasPermission('testcase:delete')) {
    items.push({
      key: 'delete',
      label: '删除',
      destructive: true,
      onSelect: () => onDelete(caseItem),
    })
  }

  const run = (item: MenuItem) => {
    setIsControlling(true)
    window.setTimeout(() => setIsControlling(false), 400)
    item.onSelect?.()
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label={`${caseItem.name} 操作`}
            disabled={isControlling}
          />
        }
      >
        <MoreHorizontal aria-hidden='true' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-48'>
        <DropdownMenuGroup>
          <DropdownMenuLabel className='truncate'>{caseItem.name}</DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        {items.map((item) =>
          item.disabled ? (
            <Tooltip key={item.key}>
              <TooltipTrigger
                render={
                  <DropdownMenuItem disabled data-variant={item.destructive ? 'destructive' : undefined} />
                }
              >
                {item.label}
              </TooltipTrigger>
              <TooltipContent>{item.disabledReason}</TooltipContent>
            </Tooltip>
          ) : (
            <DropdownMenuItem
              key={item.key}
              data-variant={item.destructive ? 'destructive' : undefined}
              onSelect={() => run(item)}
            >
              {item.key === 'favorite' && caseItem.isFavorite ? (
                <Star aria-hidden='true' className='size-4 fill-current' />
              ) : null}
              {item.label}
            </DropdownMenuItem>
          )
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function toastCase(message: string, description?: string) {
  if (description) toast.success(message, { description })
  else toast.success(message)
}
