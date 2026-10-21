/**
 * 挑选用例视图（18_挑选合并交互重设计.md §3.8.3，INT-1047/INT-1127）。
 * 用例节点 = CaseCard compact（pick-case-card.tsx）；组织维度照用例管理页
 * （分组视图/标签视图 + 平铺/交叉，复用 case-sub-view-toggle.tsx + sub-view-aggregation.ts）。
 * INT-1125 定稿：用例层组织逻辑下沉到 pick-case-org-list.tsx，本组件为用例视图容器——
 * org 状态由阶段 2 会话态（usePickOrg）持有、三视图共享，切换视图不回退。
 * 候选未返 tags/groupId（§11-7 待后端补字段）→ 全部落入「未分组」/「未设置标签」兜底桶，
 * 组织控件常显；用例卡展开 → 设备/API → result_type → 结果行叶（复用 PickTree 层级行）。
 */
import type {
  PickTreeBranch,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import type { PickOrgDimension, PickSubView } from '@/application/tasks/cherry-pick/use-pick-org'
import { PickCaseOrgList } from '@/features/tasks/cherry-pick/components/pick-case-org-list'

export interface PickCaseViewProps {
  /** 用例级分支（buildPickCaseView 输出，顶层 = 用例） */
  branches: PickTreeBranch[]
  selectedIds: ReadonlySet<number>
  onToggleLeaf: (leaf: PickTreeLeaf) => void
  onToggleBranch: (branch: PickTreeBranch, select: boolean) => void
  /** 外部「全部展开/全部收起」信号（展开用例卡 + 卡内子树） */
  expandSignal?: { all: boolean; tick: number }
  /** 组织维度（分组视图/标签视图，三视图共享，usePickOrg） */
  org: PickOrgDimension
  /** 子视图（平铺/交叉） */
  subView: PickSubView
  onOrgChange: (org: PickOrgDimension) => void
  onSubViewChange: (subView: PickSubView) => void
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
  org,
  subView,
  onOrgChange,
  onSubViewChange,
}: PickCaseViewProps) {
  return (
    <PickCaseOrgList
      branches={branches}
      selectedIds={selectedIds}
      onToggleLeaf={onToggleLeaf}
      onToggleBranch={onToggleBranch}
      expandSignal={expandSignal}
      org={org}
      subView={subView}
      onOrgChange={onOrgChange}
      onSubViewChange={onSubViewChange}
    />
  )
}
