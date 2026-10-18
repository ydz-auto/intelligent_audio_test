/**
 * 多级挑选树（18_挑选合并交互重设计.md §3.3/§3.7/§7.1，INT-600/INT-790）。
 * 五级（任务→用例→设备/API→result_type→结果行）；Checkbox 三态联动 R1-R5/R10。
 * §3.7.1 逐级收口：任务名超长 Tooltip、用例级 CaseIdBadge（点击复制）+ 算法徽章、
 * 设备/API 二选一图标；挑选页与购物车（CartTree）共用行呈现形态。
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
import { toast } from 'sonner'

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
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
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

/** 设备/API 分支图标判定：dk 段含 `api:` 前缀 → API 图标（设备分支 key 内嵌 dk） */
function isApiDeviceBranch(branch: PickTreeBranch): boolean {
  return branch.level === 'device' && branch.key.includes(':api:')
}

/** 用例 ID 展示（CaseIdBadge：不裸显 36 位 UUID，截断前 8 位 + title 全量 + 点击复制） */
function CaseIdBadge({ caseId }: { caseId: string }) {
  const short = caseId.length > 8 ? `${caseId.slice(0, 8)}…` : caseId
  return (
    <button
      type='button'
      className='text-muted-foreground hover:text-foreground shrink-0 font-mono text-[10px] tabular-nums hover:underline'
      title={`点击复制用例 ID（${caseId}）`}
      onClick={() => {
        void navigator.clipboard?.writeText(caseId).catch(() => {
          // 剪贴板写入在非安全上下文 / 权限拒绝时静默降级（localhost 可写，headless 兜底）
        })
        toast.success('用例 ID 已复制')
      }}
    >
      {short}
    </button>
  )
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
      {leaf.resultType ? (
        <Badge variant='outline' className='font-mono text-[10px]'>
          {leaf.resultType}
        </Badge>
      ) : (
        <span
          className='text-muted-foreground/60 shrink-0 text-[10px]'
          title='结果类型待后端接口（§11-2）'
        >
          待补充
        </span>
      )}
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
  const Icon = isApiDeviceBranch(branch) ? ArrowLeftRight : LEVEL_ICONS[branch.level]
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
        {/* §3.7.1 任务级：任务名超长 Tooltip（font-medium truncate 兜底） */}
        {branch.level === 'task' ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <span className='min-w-0 flex-1 truncate font-medium'>{branch.name}</span>
              }
            />
            <TooltipContent>{branch.name}</TooltipContent>
          </Tooltip>
        ) : (
          <span className='min-w-0 flex-1 truncate font-medium'>{branch.name}</span>
        )}
        {/* §3.7.1 用例级：CaseIdBadge（点击复制）+ 算法徽章（§11-7 剩余元信息落地后补全） */}
        {branch.level === 'case' && branch.caseId && <CaseIdBadge caseId={branch.caseId} />}
        {branch.level === 'case' && branch.algorithmType && (
          <Badge variant='secondary' className='shrink-0 font-mono text-[10px]'>
            {branch.algorithmType}
          </Badge>
        )}
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
