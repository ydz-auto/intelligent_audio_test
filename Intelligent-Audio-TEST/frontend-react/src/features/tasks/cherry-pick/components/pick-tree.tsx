/**
 * 多级挑选树（18_挑选合并交互重设计.md §3.3/§3.7/§7.1，INT-600/INT-790/INT-1694/INT-1819）。
 * 层级由调用方树的形状决定（用例卡 / 组织层 / 任务末级由 domain 构建器给出）；
 * Checkbox 三态联动 R1-R5/R10。§3.7.1 逐级收口：任务名超长 Tooltip、
 * 用例级 CaseIdBadge（点击复制）+ 算法徽章、设备/API 二选一图标。
 *
 * 阶段 2 树骨架来自服务端候选树：**叶的父级**节点携带 `leafFilter`、树上无子节点，
 * 展开时挂 PickLeafList 按需分页拉结果行（candidates），不随树响应一次性下发。
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
import { isLeafParentBranch } from '@/domain/lib/pick-candidate-tree'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { LeafRow } from '@/features/tasks/cherry-pick/components/pick-leaf-row'
import { PickLeafList } from '@/features/tasks/cherry-pick/components/pick-leaf-list'
import { PickCaseCard } from '@/features/tasks/cherry-pick/components/pick-case-card'
import { cn } from '@/lib/utils'

const LEVEL_ICONS = {
  task: ClipboardList,
  case: ListChecks,
  device: Smartphone,
  resultType: Tag,
  caseOrg: FolderTree,
} as const

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
  // 叶的父级节点：children 由叶明细分页按需加载（candidates），不是树响应的一部分
  const isLeafParent = isLeafParentBranch(branch)
  const hasChildren = branch.children.length > 0 || isLeafParent
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
            {isLeafParent ? (
              <PickLeafList
                filter={branch.leafFilter!}
                selectedIds={selectedIds}
                onToggleLeaf={onToggleLeaf}
                /* 任务层已渲染（level=task）时叶行不必重复任务名；单任务省略任务层时补上消歧 */
                showLeafTask={branch.level !== 'task'}
              />
            ) : (
              branch.children.map((child) =>
                child.kind === 'leaf' ? (
                  <LeafRow
                    key={child.key}
                    leaf={child}
                    selected={selectedIds.has(child.resultId)}
                    onToggle={onToggleLeaf}
                    hideDevice
                    hideResultType
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
              )
            )}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
}

/** 收集树全部分支 key（「全部展开」用）。
 * 「全部展开」只展开树骨架（到叶的父级之上）：叶的父级节点的结果行按需分页，
 * 一并展开会一次性挂载全部 `PickLeafList`（真库 2360 个过滤组合 → 2360 条并发
 * candidates 请求），故跳过；其结果行仍由用户单击该节点展开时按需拉取（§8.2.3 第 4 条）。 */
function collectAllKeys(items: PickTreeItem[]): Set<string> {
  const keys = new Set<string>()
  for (const item of items) {
    if (item.kind !== 'branch') continue
    if (isLeafParentBranch(item)) continue
    keys.add(item.key)
    collectAllKeys(item.children).forEach((k) => keys.add(k))
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
  /** 算法类型码 → 中文名（真实 /algorithm/options；子树用例卡徽章共用，INT-1687） */
  algorithmLabels?: Record<string, string>
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
  algorithmLabels,
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
    const isLeafParent = isLeafParentBranch(branch)
    return (
      <PickCaseCard
        key={branch.key}
        name={branch.name}
        caseId={branch.caseId}
        algorithmType={branch.algorithmType}
        algorithmLabels={algorithmLabels}
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
            {isLeafParent ? (
              // 单任务省略任务层：用例卡即叶的父级 → 结果行按需分页
              <PickLeafList
                filter={branch.leafFilter!}
                selectedIds={selectedIds}
                onToggleLeaf={onToggleLeaf}
                showLeafTask
              />
            ) : (
              <PickTree
                items={branch.children}
                selectedIds={selectedIds}
                onToggleLeaf={onToggleLeaf}
                onToggleBranch={onToggleBranch}
                expandSignal={expandSignal}
                algorithmLabels={algorithmLabels}
              />
            )}
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
            hideDevice
            hideResultType
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
