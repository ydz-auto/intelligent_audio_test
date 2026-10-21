/**
 * 挑选用例视图（18_挑选合并交互重设计.md §3.8.3，INT-1047）。
 * 用例节点 = CaseCard compact（pick-case-card.tsx）；组织维度照用例管理页
 * （分组视图/标签视图 + 平铺/交叉，复用 case-sub-view-toggle.tsx + sub-view-aggregation.ts）。
 * 候选未返 tags/groupId（§11-7 待后端补字段）→ 全部落入「未分组」/「未设置标签」兜底桶，
 * 组织控件常显；用例卡展开 → 设备/API → result_type → 结果行叶（复用 PickTree 层级行）。
 */
import { useMemo, useState } from 'react'

import {
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
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
import {
  CaseSubViewToggle,
  GROUP_SUB_VIEW_OPTIONS,
  TAG_SUB_VIEW_OPTIONS,
  type SubViewValue,
} from '@/features/testcases/components/case-sub-view-toggle'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'
import { PickCaseCard } from '@/features/tasks/cherry-pick/components/pick-case-card'
import { PickTree } from '@/features/tasks/cherry-pick/components/pick-tree'

/** 组织维度（§3.8.3 用例视图：分组视图/标签视图，兜底「未分组」/「未设置标签」） */
type OrgDimension = 'group' | 'tag'

/** 用例组织聚合入参（候选未返分组/标签字段 → 空集/null，全落兜底桶） */
interface CaseBranchItem extends SubViewCaseItem {
  branch: PickTreeBranch
  tags: string[]
  groupId: null
  groupName: null
  totalDuration: null
}

export interface PickCaseViewProps {
  /** 用例级分支（buildPickCaseView 输出，顶层 = 用例） */
  branches: PickTreeBranch[]
  selectedIds: ReadonlySet<number>
  onToggleLeaf: (leaf: PickTreeLeaf) => void
  onToggleBranch: (branch: PickTreeBranch, select: boolean) => void
  /** 外部「全部展开/全部收起」信号（展开用例卡 + 卡内子树） */
  expandSignal?: { all: boolean; tick: number }
}

/**
 * 用例视图：用例卡 + 分组/标签组织（照用例管理页浏览习惯）。
 * 用例卡展开区 = 设备/API → result_type → 结果行叶（复用 PickTree）。
 */
export function PickCaseView({
  branches,
  selectedIds,
  onToggleLeaf,
  onToggleBranch,
  expandSignal,
}: PickCaseViewProps) {
  const [org, setOrg] = useState<OrgDimension>('group')
  const [subView, setSubView] = useState<SubViewValue>('flat')
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
        tags: [],
        groupId: null,
        groupName: null,
        totalDuration: null,
      })),
    [branches]
  )

  /** 组织层（分组视图=按用例分组聚合，标签视图=按标签聚合；候选无分组/标签字段 → 单一兜底桶） */
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
      <div className='flex flex-wrap items-center gap-2 px-1 pt-2'>
        <Tabs
          value={org}
          onValueChange={(v) => {
            setOrg(v as OrgDimension)
            setSubView('flat')
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
          onValueChange={setSubView}
          options={org === 'group' ? GROUP_SUB_VIEW_OPTIONS : TAG_SUB_VIEW_OPTIONS}
        />
        <span className='text-muted-foreground/70 ml-auto text-[11px]'>
          候选未返分组/标签字段，按「未分组」/「未设置标签」组织（§11-7）
        </span>
      </div>

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
