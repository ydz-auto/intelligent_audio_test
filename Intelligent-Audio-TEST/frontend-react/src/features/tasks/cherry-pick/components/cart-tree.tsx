/**
 * 购物车树（18_挑选合并交互重设计.md §4.2/§4.3，INT-600）。
 * 与挑选页同层级口径（任务→用例→设备→result_type，§11-5 缺 source_result_type 折叠缺省）；
 * 管理态：勾选批量移除（R1-R5 同构）+ 单条 X + 节点「移除该组」+ 整组「移除整组」+ 失效标记。
 * 购物车抽屉与复核步骤两处共用（§4.4）。
 */
import { ChevronDown, ChevronRight, Trash2, X } from 'lucide-react'
import { useState } from 'react'

import type { CartTreeBranch, CartTreeItem, CartTreeLeaf } from '@/domain/models/cherryPick'
import {
  buildCartTree,
  collectEntryIds,
  getCartBranchSelectionState,
} from '@/domain/lib/cherry-pick-tree'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { cn } from '@/lib/utils'
import type { PickCartGroup } from '@/domain/models/cherryPick'

function LeafRow({
  leaf,
  selected,
  onToggleLeaf,
  onRemoveSingle,
  readOnly,
}: {
  leaf: CartTreeLeaf
  selected: boolean
  onToggleLeaf: (leaf: CartTreeLeaf) => void
  onRemoveSingle: (entryId: string) => void
  /** 只读态（algo_engineer：抽屉只读，增删钮隐藏，§8） */
  readOnly: boolean
}) {
  return (
    <div
      data-testid={`cart-leaf-${leaf.entryId}`}
      className='hover:bg-muted/40 flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-[13px] transition-colors'
    >
      {!readOnly && (
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggleLeaf(leaf)}
          aria-label={`条目 ${leaf.entryId}`}
        />
      )}
      <span className='min-w-0 flex-1 truncate font-medium'>{leaf.caseName}</span>
      <span className='text-muted-foreground min-w-0 max-w-40 truncate'>
        {leaf.deviceName ?? leaf.apiName ?? '—'}
      </span>
      {leaf.resultType ? (
        <Badge variant='outline' className='font-mono text-[10px]'>
          {leaf.resultType}
        </Badge>
      ) : (
        <span
          className='text-muted-foreground/60 shrink-0 text-[10px]'
          title='结果类型待后端接口（§11-5）'
        >
          结果类型待补充
        </span>
      )}
      <StatusBadge
        label={leaf.executionStatus === 'completed' ? '已完成' : '执行失败'}
        variant={leaf.executionStatus === 'completed' ? 'success' : 'danger'}
      />
      {leaf.invalid && (
        <span className='text-destructive shrink-0 text-[11px]' title='源结果已删除'>
          已失效
        </span>
      )}
      {!readOnly && (
        <Button
          variant='ghost'
          size='icon-xs'
          aria-label='移除'
          className='text-muted-foreground shrink-0'
          onClick={() => onRemoveSingle(leaf.entryId)}
        >
          <X aria-hidden='true' className='size-3.5' />
        </Button>
      )}
    </div>
  )
}

function BranchRow({
  branch,
  selectedEntryIds,
  openKeys,
  depth,
  onToggleOpen,
  onToggleLeaf,
  onToggleBranch,
  onRemoveGroup,
  onRemoveEntry,
  readOnly,
}: {
  branch: CartTreeBranch
  selectedEntryIds: ReadonlySet<string>
  openKeys: ReadonlySet<string>
  depth: number
  onToggleOpen: (key: string) => void
  onToggleLeaf: (leaf: CartTreeLeaf) => void
  onToggleBranch: (branch: CartTreeBranch, select: boolean) => void
  onRemoveGroup: (branch: CartTreeBranch) => void
  onRemoveEntry: (entryId: string) => void
  readOnly: boolean
}) {
  const state = getCartBranchSelectionState(branch, selectedEntryIds)
  const hasChildren = branch.children.length > 0
  const open = openKeys.has(branch.key)
  const indent = depth * 14 + 4

  return (
    <Collapsible open={open} onOpenChange={() => onToggleOpen(branch.key)}>
      <div
        data-testid={`cart-branch-${branch.key}`}
        className='hover:bg-muted/40 flex min-w-0 items-center gap-1.5 rounded-md py-1 pr-2 text-[13px] transition-colors'
        style={{ paddingInlineStart: indent }}
      >
        <CollapsibleTrigger
          render={
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label={open ? '收起' : '展开'}
              disabled={!hasChildren}
              className='text-muted-foreground shrink-0'
            />
          }
        >
          {hasChildren ? (
            open ? (
              <ChevronDown aria-hidden='true' className='size-3.5' />
            ) : (
              <ChevronRight aria-hidden='true' className='size-3.5' />
            )
          ) : (
            <span className='inline-block w-3.5' />
          )}
        </CollapsibleTrigger>
        {!readOnly && (
          <Checkbox
            checked={state === 'checked'}
            indeterminate={state === 'indeterminate'}
            onCheckedChange={() => onToggleBranch(branch, state !== 'checked')}
            aria-label={`${branch.name}（${branch.count} 条）`}
            className='shrink-0'
          />
        )}
        <span className='min-w-0 flex-1 truncate font-medium'>{branch.name}</span>
        {state === 'indeterminate' && (
          <span className='text-muted-foreground/70 shrink-0 text-[11px]'>
            部分选中
          </span>
        )}
        <Badge variant='secondary' className='shrink-0 font-mono text-[10px]'>
          {branch.count} 条
        </Badge>
        {!readOnly && (
          <Button
            variant='ghost'
            size='icon-xs'
            aria-label='移除该组'
            className='text-muted-foreground shrink-0'
            onClick={() => onRemoveGroup(branch)}
          >
            <Trash2 aria-hidden='true' className='size-3.5' />
          </Button>
        )}
      </div>
      {hasChildren && (
        <CollapsibleContent>
          <div className='flex flex-col'>
            {branch.children.map((child) =>
              child.kind === 'leaf' ? (
                <LeafRow
                  key={child.key}
                  leaf={child}
                  selected={selectedEntryIds.has(child.entryId)}
                  onToggleLeaf={onToggleLeaf}
                  onRemoveSingle={onRemoveEntry}
                  readOnly={readOnly}
                />
              ) : (
                <BranchRow
                  key={child.key}
                  branch={child}
                  selectedEntryIds={selectedEntryIds}
                  openKeys={openKeys}
                  depth={depth + 1}
                  onToggleOpen={onToggleOpen}
                  onToggleLeaf={onToggleLeaf}
                  onToggleBranch={onToggleBranch}
                  onRemoveGroup={onRemoveGroup}
                  onRemoveEntry={onRemoveEntry}
                  readOnly={readOnly}
                />
              )
            )}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
}

function collectAllCartKeys(items: CartTreeItem[]): Set<string> {
  const keys = new Set<string>()
  for (const item of items) {
    if (item.kind === 'branch') {
      keys.add(item.key)
      collectAllCartKeys(item.children).forEach((k) => keys.add(k))
    }
  }
  return keys
}

export interface CartTreeProps {
  groups: PickCartGroup[]
  selectedEntryIds: ReadonlySet<string>
  onToggleLeaf: (leaf: CartTreeLeaf) => void
  onToggleBranch: (branch: CartTreeBranch, select: boolean) => void
  /** 单条移除（X） */
  onRemoveEntry: (entryId: string) => void
  /** 移除节点组（用例/设备/resultType 下全部条目） */
  onRemoveNode: (entryIds: string[], levelLabel: string, name: string, count: number) => void
  /** 移除整组（来源任务） */
  onRemoveTask: (taskId: number, taskName: string, count: number) => void
  /** 只读态（algo_engineer：增删钮隐藏，§8） */
  readOnly?: boolean
  /** 全部展开信号 */
  expandSignal?: { all: boolean; tick: number }
  className?: string
}

/**
 * 购物车树：按来源任务分组（组头=任务名 + 移除整组 + 计数 Badge），组内同 3.1 层级下钻。
 */
export function CartTree({
  groups,
  selectedEntryIds,
  onToggleLeaf,
  onToggleBranch,
  onRemoveEntry,
  onRemoveNode,
  onRemoveTask,
  readOnly = false,
  expandSignal,
  className,
}: CartTreeProps) {
  const items = buildCartTree(groups)
  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set())
  const [lastSignal, setLastSignal] = useState<{ all: boolean; tick: number } | null>(
    null
  )

  if (expandSignal && expandSignal !== lastSignal) {
    setLastSignal(expandSignal)
    setOpenKeys(expandSignal.all ? collectAllCartKeys(items) : new Set())
  }

  return (
    <div className={cn('flex flex-col', className)}>
      {items.map((task, index) => {
        const group = groups[index]
        const taskState = getCartBranchSelectionState(task, selectedEntryIds)
        return (
          <section key={task.key} className='mb-2'>
            <div className='hover:bg-muted/40 flex min-w-0 items-center gap-2 rounded-md py-1 pr-2 text-[13px]'>
              {!readOnly && (
                <Checkbox
                  checked={taskState === 'checked'}
                  indeterminate={taskState === 'indeterminate'}
                  onCheckedChange={() =>
                    onToggleBranch(task, taskState !== 'checked')
                  }
                  aria-label={`${task.name}（${task.count} 条）`}
                  className='shrink-0'
                />
              )}
              <span className='min-w-0 flex-1 truncate font-medium'>
                {task.name}
              </span>
              <Badge variant='secondary' className='shrink-0 font-mono text-[10px]'>
                {task.count} 条
              </Badge>
              {!readOnly && (
                <Button
                  variant='ghost'
                  size='icon-xs'
                  aria-label='移除整组'
                  className='text-muted-foreground shrink-0'
                  onClick={() =>
                    onRemoveTask(group.taskId, task.name, task.count)
                  }
                >
                  <Trash2 aria-hidden='true' className='size-3.5' />
                </Button>
              )}
            </div>
            <BranchRow
              branch={task}
              selectedEntryIds={selectedEntryIds}
              openKeys={openKeys}
              depth={1}
              readOnly={readOnly}
              onToggleOpen={(key) =>
                setOpenKeys((prev) => {
                  const next = new Set(prev)
                  if (next.has(key)) next.delete(key)
                  else next.add(key)
                  return next
                })
              }
              onToggleLeaf={onToggleLeaf}
              onToggleBranch={onToggleBranch}
              onRemoveEntry={onRemoveEntry}
              onRemoveGroup={(branch) => {
                const levelLabel =
                  branch.level === 'device'
                    ? '设备'
                    : branch.level === 'case'
                      ? '用例'
                      : '结果类型'
                onRemoveNode(
                  collectEntryIds([branch]),
                  levelLabel,
                  branch.name,
                  branch.count
                )
              }}
            />
          </section>
        )
      })}
    </div>
  )
}
