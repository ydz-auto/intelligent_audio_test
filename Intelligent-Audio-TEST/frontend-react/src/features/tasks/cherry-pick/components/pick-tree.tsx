/**
 * 多级挑选树（18_挑选合并交互重设计.md §3.3/§7.1，INT-600）。
 * 四级分组（任务→用例→设备/API→result_type）+ 结果行叶；Checkbox 三态联动 R1-R5/R10。
 * 挑选页与购物车（CartTree）共用行呈现形态；本件用于挑选工作区。
 */
import {
  ArrowLeftRight,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  ListChecks,
  Smartphone,
  Tag,
} from 'lucide-react'
import { useState } from 'react'

import type {
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import { getBranchSelectionState } from '@/domain/lib/cherry-pick-tree'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'
import { getEvaluationStatusMeta } from '@/features/tasks/constants'
import { cn } from '@/lib/utils'

const LEVEL_ICONS = {
  task: ClipboardList,
  case: ListChecks,
  device: Smartphone,
  resultType: Tag,
} as const

/** 设备/API 二选一：叶行名称 */
function leafDeviceName(leaf: PickTreeLeaf): string {
  if (leaf.deviceName) return leaf.deviceName
  if (leaf.apiName) return leaf.apiName
  return '—'
}

function LeafRow({
  leaf,
  selected,
  onToggle,
}: {
  leaf: PickTreeLeaf
  selected: boolean
  onToggle: (leaf: PickTreeLeaf) => void
}) {
  const evalMeta = getEvaluationStatusMeta(leaf.evaluationStatus)
  return (
    <div
      data-testid={`pick-leaf-${leaf.resultId}`}
      className='hover:bg-muted/40 flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-[13px] transition-colors'
    >
      <Checkbox
        checked={selected}
        onCheckedChange={() => onToggle(leaf)}
        aria-label={`结果 ${leaf.resultId}`}
      />
      <span className='min-w-0 flex-1 truncate font-medium'>{leaf.caseName}</span>
      <span className='text-muted-foreground min-w-0 max-w-40 truncate'>
        {leafDeviceName(leaf)}
      </span>
      <Badge variant='outline' className='font-mono text-[10px]'>
        {leaf.resultType}
      </Badge>
      <StatusBadge
        label={
          leaf.executionStatus === 'completed'
            ? '已完成'
            : leaf.executionStatus === 'failed'
              ? '执行失败'
              : '已停止'
        }
        variant={
          leaf.executionStatus === 'completed'
            ? 'success'
            : leaf.executionStatus === 'failed'
              ? 'danger'
              : 'neutral'
        }
      />
      <StatusBadge label={evalMeta.label} variant={evalMeta.variant} pulse={evalMeta.pulse} />
      <span className='text-muted-foreground shrink-0 font-mono text-[10px] whitespace-nowrap tabular-nums'>
        {formatPickDateTime(leaf.createdAt)}
      </span>
      {leaf.added && (
        <span className='text-muted-foreground/70 shrink-0 text-xs' title='已在购物车'>
          已加购
        </span>
      )}
    </div>
  )
}

function BranchRow({
  branch,
  selectedIds,
  openKeys,
  depth,
  onToggleOpen,
  onToggleLeaf,
  onToggleBranch,
}: {
  branch: PickTreeBranch
  selectedIds: ReadonlySet<number>
  openKeys: ReadonlySet<string>
  depth: number
  onToggleOpen: (key: string) => void
  onToggleLeaf: (leaf: PickTreeLeaf) => void
  onToggleBranch: (branch: PickTreeBranch, select: boolean) => void
}) {
  const state = getBranchSelectionState(branch, selectedIds)
  const Icon =
    branch.level === 'device' && branch.key.startsWith('api:')
      ? ArrowLeftRight
      : LEVEL_ICONS[branch.level]
  const hasChildren = branch.children.length > 0
  const open = openKeys.has(branch.key)
  const indent = depth * 14 + 4

  return (
    <Collapsible open={open} onOpenChange={() => onToggleOpen(branch.key)}>
      <div
        data-testid={`pick-branch-${branch.key}`}
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
        <Checkbox
          checked={state === 'checked'}
          indeterminate={state === 'indeterminate'}
          onCheckedChange={() => onToggleBranch(branch, state !== 'checked')}
          aria-label={`${branch.name}（${branch.count} 条）`}
          className='shrink-0'
        />
        <Icon aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
        <span className='min-w-0 flex-1 truncate font-medium'>{branch.name}</span>
        {state === 'indeterminate' && (
          <span className='text-muted-foreground/70 shrink-0 text-[11px]'>
            部分选中
          </span>
        )}
        <Badge variant='secondary' className='shrink-0 font-mono text-[10px]'>
          {branch.count} 条
        </Badge>
      </div>
      {hasChildren && (
        <CollapsibleContent>
          <div className='flex flex-col'>
            {branch.children.map((child) =>
              child.kind === 'leaf' ? (
                <LeafRow
                  key={child.key}
                  leaf={child}
                  selected={selectedIds.has(child.resultId)}
                  onToggle={onToggleLeaf}
                />
              ) : (
                <BranchRow
                  key={child.key}
                  branch={child}
                  selectedIds={selectedIds}
                  openKeys={openKeys}
                  depth={depth + 1}
                  onToggleOpen={onToggleOpen}
                  onToggleLeaf={onToggleLeaf}
                  onToggleBranch={onToggleBranch}
                />
              )
            )}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
}

/** 收集树全部分支 key（「全部展开」用） */
function collectAllKeys(items: PickTreeItem[]): Set<string> {
  const keys = new Set<string>()
  for (const item of items) {
    if (item.kind === 'branch') {
      keys.add(item.key)
      collectAllKeys(item.children).forEach((k) => keys.add(k))
    }
  }
  return keys
}

export interface PickTreeProps {
  items: PickTreeItem[]
  selectedIds: ReadonlySet<number>
  onToggleLeaf: (leaf: PickTreeLeaf) => void
  onToggleBranch: (branch: PickTreeBranch, select: boolean) => void
  /** 外部「全部展开/全部收起」信号（{ all, tick }，tick 自增触发重放） */
  expandSignal?: { all: boolean; tick: number }
  className?: string
}

/**
 * 多级挑选树：默认收起至任务级（§6.2 层级不迷失）；「全部展开/全部收起」由外部控制。
 * 共享同一 selectedResultIds 集（Zustand 上层）。
 */
export function PickTree({
  items,
  selectedIds,
  onToggleLeaf,
  onToggleBranch,
  expandSignal,
  className,
}: PickTreeProps) {
  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set())
  const [lastSignal, setLastSignal] = useState<{ all: boolean; tick: number } | null>(
    null
  )

  if (expandSignal && expandSignal !== lastSignal) {
    setLastSignal(expandSignal)
    setOpenKeys(expandSignal.all ? collectAllKeys(items) : new Set())
  }

  return (
    <div className={cn('flex flex-col', className)}>
      {items.map((item) =>
        item.kind === 'leaf' ? (
          <LeafRow
            key={item.key}
            leaf={item}
            selected={selectedIds.has(item.resultId)}
            onToggle={onToggleLeaf}
          />
        ) : (
          <BranchRow
            key={item.key}
            branch={item}
            selectedIds={selectedIds}
            openKeys={openKeys}
            depth={0}
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
          />
        )
      )}
    </div>
  )
}
