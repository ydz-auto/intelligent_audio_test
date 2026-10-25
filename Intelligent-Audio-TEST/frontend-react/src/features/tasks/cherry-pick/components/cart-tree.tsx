/**
 * 购物车树（18_挑选合并交互重设计.md §4.2/§4.3，INT-600/INT-1047/INT-1128）。
 * 与挑选页同层级口径（任务→用例→设备→result_type，§11-5 缺 source_result_type 折叠缺省）；
 * §4.2（INT-1128）三视图切换：任务分组（默认）｜用例视图｜设备视图｜结果类型视图——
 * 三视图共享同一购物车条目集与 selectedEntryIds，切换即时生效不改变勾选/失效标记；
 * 三视图树内不设任务级分支，任务维度以 叶行来源任务名 + 顶层组头「来自 {m} 个任务」保留。
 * 管理态：勾选批量移除（R1-R5 同构）+ 单条 X + 节点「移除该组」+ 整组「移除整组」（跨任务）+ 失效标记。
 * §3.8.4 全站用例显示统一：用例节点改走 CaseCard（pick-case-card.tsx compact 变体）。
 * 购物车抽屉与复核步骤两处共用（§4.4）。
 */
import { ChevronDown, ChevronRight, Trash2, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import type {
  CartTreeBranch,
  CartTreeItem,
  CartTreeLeaf,
  PickCartGroup,
  PickCaseOrgDimension,
  PickCaseOrgSubView,
} from '@/domain/models/cherryPick'
import {
  buildCartCaseView,
  buildCartDeviceView,
  buildCartResultTypeView,
  buildCartTree,
  collectEntryIds,
  collectSourceTaskCount,
  getCartBranchSelectionState,
  PENDING_RESULT_TYPE_LABEL,
} from '@/domain/lib/cherry-pick-tree'
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
  showLeafTask,
  renderTrailing,
}: {
  leaf: CartTreeLeaf
  selected: boolean
  onToggleLeaf: (leaf: CartTreeLeaf) => void
  onRemoveSingle: (entryId: string) => void
  /** 只读态（algo_engineer：抽屉只读，增删钮隐藏，§8；容器组成区同口径） */
  readOnly: boolean
  /** §4.2 三视图：叶行携带来源任务名消歧（任务分组视图组内同源，不显示） */
  showLeafTask?: boolean
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
      {showLeafTask && (
        <span
          className='text-muted-foreground/60 max-w-28 shrink-0 truncate font-mono text-[10px] tabular-nums'
          title={`来源任务：${leaf.sourceTaskName}`}
        >
          {leaf.sourceTaskName}
        </span>
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
  showLeafTask,
  renderCaseNode,
  renderTrailing,
  renderBranchExtra,
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
  /** §4.2 三视图：叶行携带来源任务名消歧（任务分组视图不显示；CartTree 透传） */
  showLeafTask?: boolean
  /** §4.2/§3.8.4：用例级子项统一渲染 PickCaseCard（设备/结果类型视图用例层） */
  renderCaseNode?: (branch: CartTreeBranch) => ReactNode
  /** 叶行尾部附加内容（容器组成区，§5.5.3） */
  renderTrailing?: (leaf: CartTreeLeaf) => ReactNode
  /** 分支节点计数后缀（容器组成区：失败计数「· 失败 {f}」，§5.5.4） */
  renderBranchExtra?: (branch: CartTreeBranch) => ReactNode
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
            {branch.children.map((child) =>
              child.kind === 'leaf' ? (
                <LeafRow
                  key={child.key}
                  leaf={child}
                  selected={selectedEntryIds.has(child.entryId)}
                  onToggleLeaf={onToggleLeaf}
                  onRemoveSingle={onRemoveEntry}
                  readOnly={readOnly}
                  showLeafTask={showLeafTask}
                  renderTrailing={renderTrailing}
                />
              ) : child.level === 'case' && renderCaseNode ? (
                renderCaseNode(child)
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
                  showLeafTask={showLeafTask}
                  renderCaseNode={renderCaseNode}
                  renderTrailing={renderTrailing}
                  renderBranchExtra={renderBranchExtra}
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
  /** §4.2 视图：任务分组（默认）/ 用例 / 设备 / 结果类型 */
  view?: CartView
  selectedEntryIds: ReadonlySet<string>
  onToggleLeaf: (leaf: CartTreeLeaf) => void
  onToggleBranch: (branch: CartTreeBranch, select: boolean) => void
  /** 单条移除（X） */
  onRemoveEntry: (entryId: string) => void
  /** 移除节点组（用例/设备/resultType 下全部条目）；sourceTaskCount 供跨任务整组移除文案（§4.2 ②） */
  onRemoveNode: (
    entryIds: string[],
    levelLabel: string,
    name: string,
    count: number,
    sourceTaskCount?: number
  ) => void
  /** 移除整组（来源任务） */
  onRemoveTask: (taskId: number, taskName: string, count: number) => void
  /** 只读态（algo_engineer：增删钮隐藏，§8；容器组成区同口径） */
  readOnly?: boolean
  /** 全部展开信号 */
  expandSignal?: { all: boolean; tick: number }
  /** 叶行尾部附加内容（容器组成区 §5.5.3：源结果 id / 评估状态 / 时间 / 溯源钮） */
  renderLeafTrailing?: (leaf: CartTreeLeaf) => ReactNode
  /** 分支节点计数后缀（容器组成区 §5.5.4：失败计数「· 失败 {f}」） */
  renderBranchExtra?: (branch: CartTreeBranch) => ReactNode
  /**
   * 用例层组织维度（§3.8.3 A 组第 3 层）。传值时设备 / 结果类型视图在
   * result_type 之下、用例卡之上插入组织层；不传保持无组织层形状（购物车侧未接控件时不受影响）。
   */
  org?: PickCaseOrgDimension
  /** 用例层子视图（平铺 / 交叉） */
  subView?: PickCaseOrgSubView
  className?: string
}

/**
 * 购物车树：任务分组视图按来源任务分组（组头=任务名 + 移除整组 + 计数 Badge），
 * 组内同 3.1 层级下钻；用例/设备/结果类型视图为聚合树（树内无任务级分支），
 * 顶层组头「来自 {m} 个任务」+ 移除整组（跨任务）。
 * 用例节点 = CaseCard compact（§3.8.4 全站用例显示统一）。
 */
export function CartTree({
  groups,
  view = 'task',
  selectedEntryIds,
  onToggleLeaf,
  onToggleBranch,
  onRemoveEntry,
  onRemoveNode,
  onRemoveTask,
  readOnly = false,
  expandSignal,
  renderLeafTrailing,
  renderBranchExtra,
  org,
  subView = 'flat',
  className,
}: CartTreeProps) {
  /** 三视图树（§4.2 ② 纯函数重建；任务分组=现状 buildCartTree） */
  const items = useMemo<CartTreeItem[]>(() => {
    if (view === 'case') return buildCartCaseView(groups)
    if (view === 'device') return buildCartDeviceView(groups, org, subView)
    if (view === 'resultType') return buildCartResultTypeView(groups, org, subView)
    return buildCartTree(groups)
  }, [view, groups, org, subView])

  /** 三视图叶行携带来源任务名消歧（任务分组视图组内同源，不显示） */
  const showLeafTask = view !== 'task'

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

  /** 节点「移除该组」确认（层级文案，§4.3） */
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
    onRemoveNode(
      collectEntryIds([branch]),
      levelLabel,
      branch.name,
      branch.count
    )
  }

  /** 三视图顶层组头「移除整组」（跨任务整组移除，§4.2 ②：确认文案带来源任务数） */
  const handleRemoveTopGroup = (branch: CartTreeBranch) => {
    const levelLabel =
      branch.level === 'device'
        ? '设备'
        : branch.level === 'case'
          ? '用例'
          : branch.level === 'caseOrg'
            ? branch.orgKind === 'tag'
              ? '标签组'
              : '分组'
            : '结果类型'
    onRemoveNode(
      collectEntryIds([branch]),
      levelLabel,
      branch.name,
      branch.count,
      collectSourceTaskCount([branch])
    )
  }

  /**
   * 用例节点（CaseCard compact，§4.2/§3.8.4）+ 卡内 device/result_type/leaf 子树。
   * topLevel=true（用例视图顶层）：计数旁「来自 {m} 个任务」+「移除整组」跨任务（§4.2 ② mermaid）；
   * 否则节点「移除该组」。设备/结果类型视图用例层经 BranchRow 的 renderCaseNode 路由复用本函数。
   */
  const renderCaseNode = (branch: CartTreeBranch, topLevel = false) => {
    const open = openKeys.has(branch.key)
    const taskCount = collectSourceTaskCount([branch])
    return (
      <PickCaseCard
        key={branch.key}
        name={branch.name}
        caseId={branch.caseId}
        count={branch.count}
        state={getCartBranchSelectionState(branch, selectedEntryIds)}
        onToggle={(select) => onToggleBranch(branch, select)}
        open={open}
        onToggleOpen={() => toggleOpenKey(branch.key)}
        readOnly={readOnly}
        badgeLeading={
          topLevel && taskCount > 0 ? (
            <span className='text-muted-foreground/70 shrink-0 text-[11px]'>
              来自 {taskCount} 个任务
            </span>
          ) : undefined
        }
        actions={
          !readOnly ? (
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label={topLevel ? '移除整组' : '移除该组'}
              className='text-muted-foreground shrink-0'
              onClick={() =>
                topLevel
                  ? handleRemoveTopGroup(branch)
                  : handleRemoveGroup(branch)
              }
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
                  showLeafTask={showLeafTask}
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
                  showLeafTask={showLeafTask}
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

  /** 子项统一渲染（任务分组视图与三视图共用；depth 从顶向下递增） */
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
          showLeafTask={showLeafTask}
          renderTrailing={renderLeafTrailing}
        />
      )
    }
    if (item.level === 'case') {
      return renderCaseNode(item)
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
        showLeafTask={showLeafTask}
        renderCaseNode={renderCaseNode}
        renderTrailing={renderLeafTrailing}
        renderBranchExtra={renderBranchExtra}
      />
    )
  }

  /** 三视图顶层组头（用例/设备/结果类型；跨任务「来自 {m} 个任务」+ 移除整组，§4.2 ②） */
  const renderTopGroup = (branch: CartTreeBranch, index: number) => {
    /** 用例视图顶层：用例节点 = PickCaseCard（compact 计数 + 「来自 {m} 个任务」+ 移除整组，§4.2 ② mermaid） */
    if (branch.level === 'case') {
      return (
        <section key={branch.key} className='mb-2'>
          {renderCaseNode(branch, true)}
        </section>
      )
    }
    const taskCount = collectSourceTaskCount([branch])
    const group = groups[index] // 任务分组视图下取来源任务组
    const state = getCartBranchSelectionState(branch, selectedEntryIds)
    const isTaskView = view === 'task'
    return (
      <section key={branch.key} className='mb-2'>
        <div className='hover:bg-muted/40 flex min-w-0 items-center gap-2 rounded-md py-1 pr-2 text-[13px]'>
          {!readOnly && (
            <Checkbox
              checked={state === 'checked'}
              indeterminate={state === 'indeterminate'}
              onCheckedChange={() =>
                onToggleBranch(branch, state !== 'checked')
              }
              aria-label={`${branch.name}（${branch.count} 条）`}
              className='shrink-0'
            />
          )}
          <span className='min-w-0 flex-1 truncate font-medium'>
            {branch.name}
          </span>
          {!isTaskView && taskCount > 0 && (
            <span className='text-muted-foreground/70 shrink-0 text-[11px]'>
              来自 {taskCount} 个任务
            </span>
          )}
          {!isTaskView && state === 'indeterminate' && (
            <span className='text-muted-foreground/70 shrink-0 text-[11px]'>
              部分选中
            </span>
          )}
          <Badge variant='secondary' className='shrink-0 font-mono text-[10px]'>
            {branch.count} 条
          </Badge>
          {renderBranchExtra?.(branch)}
          {!readOnly &&
            (isTaskView ? (
              <Button
                variant='ghost'
                size='icon-xs'
                aria-label='移除整组'
                className='text-muted-foreground shrink-0'
                onClick={() =>
                  group && onRemoveTask(group.taskId, branch.name, branch.count)
                }
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
              </Button>
            ) : (
              <Button
                variant='ghost'
                size='icon-xs'
                aria-label='移除整组'
                className='text-muted-foreground shrink-0'
                onClick={() => handleRemoveTopGroup(branch)}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
              </Button>
            ))}
        </div>
        <div className='mt-1 flex flex-col gap-2'>
          {branch.children.map((child) => renderCartItem(child, 1))}
        </div>
      </section>
    )
  }

  return (
    <div className={cn('flex flex-col', className)}>
      {items.map((item, index) => renderTopGroup(item as CartTreeBranch, index))}
    </div>
  )
}
