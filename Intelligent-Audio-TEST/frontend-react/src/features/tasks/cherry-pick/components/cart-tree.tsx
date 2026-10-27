/**
 * 购物车树（INT-1694 二次口径，负责人 2026-10-24）。
 * 四视图 = 任务视图（默认，任务在第一级，任务下再分 用例 / 设备 / 结果类型 子模式）
 * ＋ 基础三视图 用例视图 / 设备视图 / 结果类型视图（任务在最末一级，即叶的前一级）。
 * A 组三视图共享同一购物车条目集与 selectedEntryIds，任务之上的节点跨任务共享；
 * 切换视图 / 子模式不改变勾选态与失效标记（§4.2）。
 * 用例层组织（分组/标签 + 平铺/交叉）出现在用例视图顶层与任务视图用例子模式下，
 * 复用阶段 2 的 PickCaseOrgControls + sub-view-aggregation 同一套语义。
 * 所有分支节点（含任务节点）统一：名称 + 计数「{n} 条」+ 三态 Checkbox + 展开/收起 +
 * 「移除该组」（= 本节点下全部条目，不跨节点）。叶行不再显示来源任务名。
 * §3.8.4 全站用例显示统一：用例节点走 CaseCard（pick-case-card.tsx compact 变体）。
 * 购物车抽屉与复核步骤两处共用（§4.4）；预览步骤只读复用同一棵树。
 */
import { ChevronDown, ChevronRight, Trash2, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import type {
  CartTreeBranch,
  CartTreeItem,
  CartTreeLeaf,
  PickCartGroup,
} from '@/domain/models/cherryPick'
import {
  buildCartCaseView,
  buildCartDeviceView,
  buildCartResultTypeView,
  buildCartTaskView,
  collectEntryIds,
  getCartBranchSelectionState,
  PENDING_RESULT_TYPE_LABEL,
  type CartTaskSubView,
} from '@/domain/lib/cherry-pick-tree'
import {
  groupCasesByCaseGroup,
  groupCasesByTag,
} from '@/domain/lib/sub-view-aggregation'
import type { PickOrgDimension, PickSubView } from '@/application/tasks/cherry-pick/use-pick-org'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { cn } from '@/lib/utils'
import { PickCaseCard } from '@/features/tasks/cherry-pick/components/pick-case-card'
import type { CartView } from '@/features/tasks/cherry-pick/components/cart-view-switcher'

/** 执行状态文案（§5.5.4 叶行：已完成 success / 已失败 destructive / 已停止 neutral） */
function executionLabel(status: string): string {
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '执行失败'
  if (status === 'stopped') return '已停止'
  return '状态未知'
}

function executionVariant(status: string): 'success' | 'danger' | 'neutral' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'neutral'
}

function LeafRow({
  leaf,
  selected,
  onToggleLeaf,
  onRemoveSingle,
  readOnly,
  renderTrailing,
}: {
  leaf: CartTreeLeaf
  selected: boolean
  onToggleLeaf: (leaf: CartTreeLeaf) => void
  onRemoveSingle: (entryId: string) => void
  /** 只读态（algo_engineer：抽屉只读，增删钮隐藏，§8；容器组成区同口径） */
  readOnly: boolean
  /** 叶行尾部附加内容（容器组成区：源结果 id / 评估状态 / 时间 / 溯源钮，§5.5.3） */
  renderTrailing?: (leaf: CartTreeLeaf) => ReactNode
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
      {/* INT-2098：叶行不重复显示用例名（用例卡已展示），设备/API 名升为主列 */}
      <span className='min-w-0 flex-1 truncate font-medium'>
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
        label={executionLabel(leaf.executionStatus)}
        variant={executionVariant(leaf.executionStatus)}
      />
      {renderTrailing?.(leaf)}
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

/** 用例层组织入参（购物车条目缺 tags/group 时落「未设置标签 / 未分组」兜底桶） */
interface CartCaseOrgItem {
  branch: CartTreeBranch
  tags: string[]
  groupId: string | null
  groupName: string | null
  totalDuration: number | null
}

interface BranchRowProps {
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
  /** 用例层组织：children 全为用例级分支时改由组织列表渲染（用例视图 / 任务视图用例子模式） */
  renderCaseLayer?: (branches: CartTreeBranch[]) => ReactNode
  /** 用例卡节点渲染（CaseCard） */
  renderCaseNode: (branch: CartTreeBranch) => ReactNode
  /** 叶行尾部附加内容（容器组成区，§5.5.3） */
  renderTrailing?: (leaf: CartTreeLeaf) => ReactNode
  /** 分支节点计数后缀（容器组成区：失败计数「· 失败 {f}」，§5.5.4） */
  renderBranchExtra?: (branch: CartTreeBranch) => ReactNode
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
  renderCaseLayer,
  renderCaseNode,
  renderTrailing,
  renderBranchExtra,
}: BranchRowProps) {
  const state = getCartBranchSelectionState(branch, selectedEntryIds)
  const hasChildren = branch.children.length > 0
  const open = openKeys.has(branch.key)
  const indent = depth * 14 + 4

  /** 用例层（children 全为用例级分支 → 走组织列表，替代内联文本行） */
  const caseLayerChildren =
    renderCaseLayer && hasChildren && branch.children.every((c) => c.kind === 'branch' && c.level === 'case')
      ? (branch.children as CartTreeBranch[])
      : null

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
        {/* §3.7.2：历史快照缺 source_result_type → 「结果类型待补充」组 Tooltip 说明 */}
        {branch.level === 'resultType' && branch.name === PENDING_RESULT_TYPE_LABEL ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <span className='min-w-0 flex-1 truncate font-medium'>{branch.name}</span>
              }
            />
            <TooltipContent>结果类型待后端接口（§11-5）</TooltipContent>
          </Tooltip>
        ) : (
          <span className='min-w-0 flex-1 truncate font-medium'>{branch.name}</span>
        )}
        {state === 'indeterminate' && (
          <span className='text-muted-foreground/70 shrink-0 text-[11px]'>
            部分选中
          </span>
        )}
        <Badge variant='secondary' className='shrink-0 font-mono text-[10px]'>
          {branch.count} 条
        </Badge>
        {renderBranchExtra?.(branch)}
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
            {caseLayerChildren ? (
              renderCaseLayer?.(caseLayerChildren)
            ) : (
              branch.children.map((child) =>
                child.kind === 'leaf' ? (
                  <LeafRow
                    key={child.key}
                    leaf={child}
                    selected={selectedEntryIds.has(child.entryId)}
                    onToggleLeaf={onToggleLeaf}
                    onRemoveSingle={onRemoveEntry}
                    readOnly={readOnly}
                    renderTrailing={renderTrailing}
                  />
                ) : child.level === 'case' ? (
                  <div key={child.key}>{renderCaseNode(child)}</div>
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
                    renderCaseLayer={renderCaseLayer}
                    renderCaseNode={renderCaseNode}
                    renderTrailing={renderTrailing}
                    renderBranchExtra={renderBranchExtra}
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
  /** 视图：任务（默认）/ 用例 / 设备 / 结果类型 */
  view?: CartView
  /** 任务视图下的子模式：用例 / 设备 / 结果类型 */
  taskSubView?: CartTaskSubView
  selectedEntryIds: ReadonlySet<string>
  onToggleLeaf: (leaf: CartTreeLeaf) => void
  onToggleBranch: (branch: CartTreeBranch, select: boolean) => void
  /** 单条移除（X） */
  onRemoveEntry: (entryId: string) => void
  /** 移除节点组（本节点下全部条目，不跨节点） */
  onRemoveNode: (entryIds: string[], levelLabel: string, name: string, count: number) => void
  /** 移除整组（来源任务）：INT-1694 二次口径改为所有分支节点统一走「移除该组」，本 prop 保留供
   *  容器组成区（INT-1711）等调用方透传，只读态下不会触发 */
  onRemoveTask?: (taskId: number, taskName: string, count: number) => void
  /** 只读态（algo_engineer：增删钮隐藏，§8；容器组成区同口径） */
  readOnly?: boolean
  /** 全部展开信号 */
  expandSignal?: { all: boolean; tick: number }
  /** 叶行尾部附加内容（容器组成区 §5.5.3：源结果 id / 评估状态 / 时间 / 溯源钮） */
  renderLeafTrailing?: (leaf: CartTreeLeaf) => ReactNode
  /** 分支节点计数后缀（容器组成区 §5.5.4：失败计数「· 失败 {f}」） */
  renderBranchExtra?: (branch: CartTreeBranch) => ReactNode
  /** 用例层组织维度（用例视图 / 任务视图用例子模式） */
  org?: PickOrgDimension
  /** 用例层子视图（平铺 / 交叉） */
  subView?: PickSubView
  className?: string
}

/**
 * 购物车树：任务视图按任务分组（任务节点 + 子模式展开）；A 组三视图为跨任务聚合树，
 * 最末一级分支是任务。用例节点 = CaseCard compact（§3.8.4 全站用例显示统一）。
 */
export function CartTree({
  groups,
  view = 'task',
  taskSubView = 'case',
  selectedEntryIds,
  onToggleLeaf,
  onToggleBranch,
  onRemoveEntry,
  onRemoveNode,
  readOnly = false,
  expandSignal,
  renderLeafTrailing,
  renderBranchExtra,
  org = 'group',
  subView = 'flat',
  className,
}: CartTreeProps) {
  /** 视图树（纯函数重建；A 组三视图任务在最末一级，任务视图任务在第一级；
   *  设备/结果类型视图与子模式的组织层在 result_type/设备 之下、用例卡之上） */
  const items = useMemo<CartTreeItem[]>(() => {
    if (view === 'task') return buildCartTaskView(groups, taskSubView, org, subView)
    if (view === 'device') return buildCartDeviceView(groups, org, subView)
    if (view === 'resultType') return buildCartResultTypeView(groups, org, subView)
    return buildCartCaseView(groups)
  }, [view, taskSubView, groups, org, subView])

  /** 用例层组件组织只在「用例视图顶层」与「任务视图用例子模式」生效——
   *  设备/结果类型（含任务视图对应子模式）的组织层由树内 caseOrg 组头节点渲染 */
  const hasCaseOrgLayer = view === 'case' || (view === 'task' && taskSubView === 'case')

  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set())
  const [lastSignal, setLastSignal] = useState<{ all: boolean; tick: number } | null>(
    null
  )

  if (expandSignal && expandSignal !== lastSignal) {
    setLastSignal(expandSignal)
    setOpenKeys(expandSignal.all ? collectAllCartKeys(items) : new Set())
  }

  const toggleOpenKey = (key: string) =>
    setOpenKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  /** 节点「移除该组」（本节点下全部条目，层级文案，§4.3） */
  const handleRemoveGroup = (branch: CartTreeBranch) => {
    const levelLabel =
      branch.level === 'device'
        ? '设备'
        : branch.level === 'case'
          ? '用例'
          : branch.level === 'resultType'
            ? '结果类型'
            : branch.level === 'caseOrg'
              ? branch.orgKind === 'tag'
                ? '标签组'
                : '分组'
              : '任务'
    onRemoveNode(collectEntryIds([branch]), levelLabel, branch.name, branch.count)
  }

  /** 用例节点（CaseCard compact，§4.2/§3.8.4）+ 卡内子树 */
  const renderCaseNode = (branch: CartTreeBranch) => {
    const open = openKeys.has(branch.key)
    return (
      <PickCaseCard
        key={branch.key}
        name={branch.name}
        caseId={branch.caseId}
        tags={branch.tags ?? []}
        totalDuration={branch.totalDuration ?? null}
        rounds={branch.rounds ?? null}
        count={branch.count}
        state={getCartBranchSelectionState(branch, selectedEntryIds)}
        onToggle={(select) => onToggleBranch(branch, select)}
        open={open}
        onToggleOpen={() => toggleOpenKey(branch.key)}
        actions={
          !readOnly ? (
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='移除该组'
              className='text-muted-foreground shrink-0'
              onClick={() => handleRemoveGroup(branch)}
            >
              <Trash2 aria-hidden='true' className='size-3.5' />
            </Button>
          ) : undefined
        }
      >
        {open ? (
          <div className='space-y-0.5 px-3 pb-3'>
            {branch.children.map((child) =>
              child.kind === 'leaf' ? (
                <LeafRow
                  key={child.key}
                  leaf={child}
                  selected={selectedEntryIds.has(child.entryId)}
                  onToggleLeaf={onToggleLeaf}
                  onRemoveSingle={onRemoveEntry}
                  readOnly={readOnly}
                  renderTrailing={renderLeafTrailing}
                />
              ) : (
                <BranchRow
                  key={child.key}
                  branch={child}
                  selectedEntryIds={selectedEntryIds}
                  openKeys={openKeys}
                  depth={2}
                  onToggleOpen={toggleOpenKey}
                  onToggleLeaf={onToggleLeaf}
                  onToggleBranch={onToggleBranch}
                  onRemoveGroup={handleRemoveGroup}
                  onRemoveEntry={onRemoveEntry}
                  readOnly={readOnly}
                  renderCaseNode={renderCaseNode}
                  renderTrailing={renderLeafTrailing}
                  renderBranchExtra={renderBranchExtra}
                />
              )
            )}
          </div>
        ) : undefined}
      </PickCaseCard>
    )
  }

  /** 用例层组织列表（分组/标签 + 平铺/交叉）：用例卡片流，勾选/移除矩阵不变 */
  const renderCaseOrgLayer = (branches: CartTreeBranch[]) => {
    const caseItems: CartCaseOrgItem[] = branches.map((b) => ({
      branch: b,
      tags: b.tags ?? [],
      groupId: b.groupId ?? null,
      groupName: b.groupName ?? null,
      totalDuration: b.totalDuration ?? null,
    }))
    const orgGroups =
      org === 'tag' ? groupCasesByTag(caseItems, []) : groupCasesByCaseGroup(caseItems)

    const renderGroupBody = (cases: CartCaseOrgItem[], groupKey: string) => {
      if (subView === 'flat') {
        return <div className='space-y-2'>{cases.map((c) => renderCaseNode(c.branch))}</div>
      }
      const subGroups =
        org === 'group' ? groupCasesByTag(cases, []) : groupCasesByCaseGroup(cases)
      return (
        <div className='space-y-2'>
          {subGroups.map((g) => (
            <div key={`${groupKey}-${g.key}`} className='space-y-2'>
              <CaseSubGroupHeader
                group={g}
                muted={g.key === '__untagged__' || g.key === '__ungrouped__'}
              />
              <div className='space-y-2'>{g.cases.map((c) => renderCaseNode(c.branch))}</div>
            </div>
          ))}
        </div>
      )
    }

    return (
      <div className='flex flex-col gap-2'>
        {orgGroups.length === 0 ? (
          <p className='text-muted-foreground px-2 py-6 text-center text-sm'>
            无符合条件的用例
          </p>
        ) : (
          orgGroups.map((g) => (
            <div
              key={g.key}
              className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'
            >
              <CaseSubGroupHeader
                group={g}
                muted={g.key === '__untagged__' || g.key === '__ungrouped__'}
              />
              <div className='space-y-2 border-t px-3 py-3'>
                {renderGroupBody(g.cases, g.key)}
              </div>
            </div>
          ))
        )}
      </div>
    )
  }

  /** 子项统一渲染（所有视图共用；depth 从顶向下递增） */
  const renderCartItem = (item: CartTreeItem, depth: number) => {
    if (item.kind === 'leaf') {
      return (
        <LeafRow
          key={item.key}
          leaf={item}
          selected={selectedEntryIds.has(item.entryId)}
          onToggleLeaf={onToggleLeaf}
          onRemoveSingle={onRemoveEntry}
          readOnly={readOnly}
          renderTrailing={renderLeafTrailing}
        />
      )
    }
    if (item.level === 'case') {
      return <div key={item.key}>{renderCaseNode(item)}</div>
    }
    return (
      <BranchRow
        key={item.key}
        branch={item}
        selectedEntryIds={selectedEntryIds}
        openKeys={openKeys}
        depth={depth}
        onToggleOpen={toggleOpenKey}
        onToggleLeaf={onToggleLeaf}
        onToggleBranch={onToggleBranch}
        onRemoveGroup={handleRemoveGroup}
        onRemoveEntry={onRemoveEntry}
        readOnly={readOnly}
        renderCaseLayer={hasCaseOrgLayer ? renderCaseOrgLayer : undefined}
        renderCaseNode={renderCaseNode}
        renderTrailing={renderLeafTrailing}
        renderBranchExtra={renderBranchExtra}
      />
    )
  }

  /** 顶层即用例层（用例视图）：顶层直接走组织列表 */
  const rootIsCaseLayer =
    hasCaseOrgLayer &&
    items.length > 0 &&
    items.every((n) => n.kind === 'branch' && n.level === 'case')

  return (
    <div className={cn('flex flex-col', className)}>
      {rootIsCaseLayer
        ? renderCaseOrgLayer(items as CartTreeBranch[])
        : items.map((item) => renderCartItem(item, 0))}
    </div>
  )
}
