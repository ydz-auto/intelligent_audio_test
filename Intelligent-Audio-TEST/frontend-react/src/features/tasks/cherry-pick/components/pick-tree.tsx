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
  FolderTree,
  ListChecks,
  Smartphone,
  Tag,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
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
import { PickCaseCard } from '@/features/tasks/cherry-pick/components/pick-case-card'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'
import { getEvaluationStatusMeta } from '@/features/tasks/constants'
import { cn } from '@/lib/utils'

const LEVEL_ICONS = {
  task: ClipboardList,
  case: ListChecks,
  device: Smartphone,
  resultType: Tag,
  caseOrg: FolderTree,
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
  renderCaseNode,
}: {
  branch: PickTreeBranch
  selectedIds: ReadonlySet<number>
  openKeys: ReadonlySet<string>
  depth: number
  onToggleOpen: (key: string) => void
  onToggleLeaf: (leaf: PickTreeLeaf) => void
  onToggleBranch: (branch: PickTreeBranch, select: boolean) => void
  /** 用例卡渲染（INT-1694：用例节点 = CaseCard compact，组织层组头下挂用例卡） */
  renderCaseNode?: (branch: PickTreeBranch) => ReactNode
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
        {/* §3.7.1 用例级：CaseIdBadge（点击复制）+ 算法徽章（§11-7 元信息已随分支携带） */}
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
              ) : child.level === 'case' && renderCaseNode ? (
                <div key={child.key}>{renderCaseNode(child)}</div>
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
                  renderCaseNode={renderCaseNode}
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
 * 多级挑选树（INT-1694 三次口径）：层级由调用方树的形状决定（任务在末级、组织层在
 * result_type 之下用例卡之上时也由本组件统一渲染行形态）；用例节点 = CaseCard compact，
 * 组织层组头 = 普通分支行（名称 + 计数 + 三态 Checkbox + 展开/收起）。
 * 「全部展开/全部收起」由外部控制。共享同一 selectedResultIds 集（Zustand 上层）。
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

  const toggleOpenKey = (key: string) =>
    setOpenKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  /** 用例节点（CaseCard compact，§3.8.4 全站用例显示统一）+ 卡内子树 */
  const renderCaseNode = (branch: PickTreeBranch) => {
    const open = openKeys.has(branch.key)
    return (
      <PickCaseCard
        key={branch.key}
        name={branch.name}
        caseId={branch.caseId}
        algorithmType={branch.algorithmType}
        tags={branch.tags ?? []}
        totalDuration={branch.totalDuration ?? null}
        rounds={branch.rounds ?? null}
        count={branch.count}
        state={getBranchSelectionState(branch, selectedIds)}
        onToggle={(select) => onToggleBranch(branch, select)}
        open={open}
        onToggleOpen={() => toggleOpenKey(branch.key)}
      >
        {open ? (
          <div className='space-y-0.5 px-3 pb-3'>
            <PickTree
              items={branch.children}
              selectedIds={selectedIds}
              onToggleLeaf={onToggleLeaf}
              onToggleBranch={onToggleBranch}
              expandSignal={expandSignal}
            />
          </div>
        ) : undefined}
      </PickCaseCard>
    )
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
        ) : item.level === 'case' ? (
          <div key={item.key}>{renderCaseNode(item)}</div>
        ) : (
          <BranchRow
            key={item.key}
            branch={item}
            selectedIds={selectedIds}
            openKeys={openKeys}
            depth={0}
            onToggleOpen={toggleOpenKey}
            onToggleLeaf={onToggleLeaf}
            onToggleBranch={onToggleBranch}
            renderCaseNode={renderCaseNode}
          />
        )
      )}
    </div>
  )
}
