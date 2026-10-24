/**
 * 用例层组织（18_挑选合并交互重设计.md §3.8.3 用例层组织，INT-1125 定稿 / INT-1127 实施）。
 * 分组视图/标签视图 Tabs + 平铺/交叉子视图 + 用例卡（PickCaseCard）+ 子组头（CaseSubGroupHeader）——
 * 供用例视图顶层与设备/结果类型视图用例层（每 result_type/设备 节点下）共用；
 * 复用 case-sub-view-toggle.tsx + sub-view-aggregation.ts 同款语义。
 * INT-1497 §11-7：候选已返用例域真名 tags/group_id/group_name/duration/rounds，
 * 用例层按真实分组/标签聚合，仅在字段缺省（null/空）时落「未分组」/「未设置标签」兜底桶。
 */
import { useMemo, useState } from 'react'

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type {
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import { getBranchSelectionState } from '@/domain/lib/cherry-pick-tree'
import {
  groupCasesByCaseGroup,
  groupCasesByTag,
  type SubViewCaseItem,
} from '@/domain/lib/sub-view-aggregation'
import type { PickOrgDimension, PickSubView } from '@/application/tasks/cherry-pick/use-pick-org'
import {
  CaseSubViewToggle,
  GROUP_SUB_VIEW_OPTIONS,
  TAG_SUB_VIEW_OPTIONS,
} from '@/features/testcases/components/case-sub-view-toggle'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'
import { PickCaseCard } from '@/features/tasks/cherry-pick/components/pick-case-card'
import { PickTree } from '@/features/tasks/cherry-pick/components/pick-tree'

/** 用例组织聚合入参（用例级分支携带 §11-7 真名；字段缺省才落兜底桶） */
interface CaseBranchItem extends SubViewCaseItem {
  branch: PickTreeBranch
  tags: string[]
  groupId: string | null
  groupName: string | null
  totalDuration: number | null
  rounds: number | null
}

/** 组织控件（分组视图/标签视图 + 平铺/交叉子视图）——设备/结果类型视图在视图级渲染一次 */
export function PickCaseOrgControls({
  org,
  subView,
  onOrgChange,
  onSubViewChange,
  hint = '候选未返分组/标签字段，按「未分组」/「未设置标签」组织（§11-7）',
}: {
  org: PickOrgDimension
  subView: PickSubView
  onOrgChange: (org: PickOrgDimension) => void
  onSubViewChange: (subView: PickSubView) => void
  /** 右端提示文案；传 null 隐藏（数据源已带真实分组/标签时，如容器组成区） */
  hint?: string | null
}) {
  return (
    <div className='flex flex-wrap items-center gap-2 px-1'>
      <Tabs
        value={org}
        onValueChange={(v) => {
          onOrgChange(v as PickOrgDimension)
          onSubViewChange('flat')
        }}
        aria-label='用例组织方式'
      >
        <TabsList className='h-7 gap-0.5 p-0.5'>
          <TabsTrigger value='group' className='px-2 text-xs'>
            分组视图
          </TabsTrigger>
          <TabsTrigger value='tag' className='px-2 text-xs'>
            标签视图
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <CaseSubViewToggle
        value={subView}
        onValueChange={onSubViewChange}
        options={org === 'group' ? GROUP_SUB_VIEW_OPTIONS : TAG_SUB_VIEW_OPTIONS}
      />
      {hint && (
        <span className='text-muted-foreground/70 ml-auto text-[11px]'>{hint}</span>
      )}
    </div>
  )
}

export interface PickCaseOrgListProps {
  /** 用例级分支（buildPickCaseView / buildPickDeviceView / buildPickResultTypeView 输出用例节点） */
  branches: PickTreeBranch[]
  selectedIds: ReadonlySet<number>
  onToggleLeaf: (leaf: PickTreeLeaf) => void
  onToggleBranch: (branch: PickTreeBranch, select: boolean) => void
  /** 外部「全部展开/全部收起」信号（展开用例卡 + 卡内子树） */
  expandSignal?: { all: boolean; tick: number }
  /** 组织维度（分组视图/标签视图，三视图共享） */
  org: PickOrgDimension
  /** 子视图（平铺/交叉） */
  subView: PickSubView
  onOrgChange: (org: PickOrgDimension) => void
  onSubViewChange: (subView: PickSubView) => void
  /** 设备/结果类型视图节点内嵌时不重复渲染组织控件（视图级已渲染一次） */
  showControls?: boolean
}

/**
 * 用例层组织列表：组织控件（可选）+ 组织后的用例卡流。
 * 组织只影响用例层视觉分组，勾选联动与 selectedResultIds 不变。
 */
export function PickCaseOrgList({
  branches,
  selectedIds,
  onToggleLeaf,
  onToggleBranch,
  expandSignal,
  org,
  subView,
  onOrgChange,
  onSubViewChange,
  showControls = true,
}: PickCaseOrgListProps) {
  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set())
  const [lastSignal, setLastSignal] = useState<{
    all: boolean
    tick: number
  } | null>(null)

  if (expandSignal && expandSignal !== lastSignal) {
    setLastSignal(expandSignal)
    setOpenKeys(expandSignal.all ? new Set(branches.map((b) => b.key)) : new Set())
  }

  const caseItems = useMemo<CaseBranchItem[]>(
    () =>
      branches.map((b) => ({
        branch: b,
        tags: b.tags ?? [],
        groupId: b.groupId ?? null,
        groupName: b.groupName ?? null,
        totalDuration: b.totalDuration ?? null,
        rounds: b.rounds ?? null,
      })),
    [branches]
  )

  /** 组织层（分组视图=按用例分组聚合，标签视图=按标签聚合；字段缺省才落兜底桶） */
  const orgGroups = useMemo(() => {
    if (org === 'group') return groupCasesByCaseGroup(caseItems)
    return groupCasesByTag(caseItems, [])
  }, [org, caseItems])

  const toggleCaseOpen = (key: string) =>
    setOpenKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const renderCaseCard = (item: CaseBranchItem) => {
    const b = item.branch
    return (
      <PickCaseCard
        key={b.key}
        name={b.name}
        caseId={b.caseId}
        algorithmType={b.algorithmType}
        tags={b.tags}
        totalDuration={b.totalDuration}
        rounds={b.rounds}
        count={b.count}
        state={getBranchSelectionState(b, selectedIds)}
        onToggle={(select) => onToggleBranch(b, select)}
        open={openKeys.has(b.key)}
        onToggleOpen={() => toggleCaseOpen(b.key)}
      >
        {openKeys.has(b.key) ? (
          <div className='space-y-0.5 px-3 pb-3'>
            <PickTree
              items={b.children as PickTreeItem[]}
              selectedIds={selectedIds}
              onToggleLeaf={onToggleLeaf}
              onToggleBranch={onToggleBranch}
              expandSignal={expandSignal}
              showLeafTask
            />
          </div>
        ) : undefined}
      </PickCaseCard>
    )
  }

  /** 组内内容：平铺 或 交叉分组（分组视图内按标签 / 标签视图内按用例分组） */
  const renderGroupBody = (cases: CaseBranchItem[]) => {
    if (subView === 'flat') {
      return <div className='space-y-2'>{cases.map(renderCaseCard)}</div>
    }
    if (org === 'group') {
      const groups = groupCasesByTag(cases, [])
      return (
        <div className='space-y-2'>
          {groups.map((g) => (
            <div key={g.key} className='space-y-2'>
              <CaseSubGroupHeader group={g} muted={g.key === '__untagged__'} />
              <div className='space-y-2'>{g.cases.map(renderCaseCard)}</div>
            </div>
          ))}
        </div>
      )
    }
    const groups = groupCasesByCaseGroup(cases)
    return (
      <div className='space-y-2'>
        {groups.map((g) => (
          <div key={g.key} className='space-y-2'>
            <CaseSubGroupHeader group={g} muted={g.key === '__ungrouped__'} />
            <div className='space-y-2'>{g.cases.map(renderCaseCard)}</div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className='flex flex-col gap-2'>
      {showControls && (
        <div className='px-1 pt-2'>
          <PickCaseOrgControls
            org={org}
            subView={subView}
            onOrgChange={onOrgChange}
            onSubViewChange={onSubViewChange}
          />
        </div>
      )}

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
              {renderGroupBody(g.cases)}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
