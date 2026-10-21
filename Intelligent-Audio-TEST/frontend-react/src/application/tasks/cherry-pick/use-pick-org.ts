/**
 * 三视图用例层组织状态（18_挑选合并交互重设计.md §3.8.3 用例层组织，INT-1125 定稿）。
 * org 维度（分组视图/标签视图）+ 子视图（平铺/交叉）为阶段 2 会话态、三视图共享——
 * 切换视图保持组织偏好；与 selectedResultIds 解耦，组织只影响用例层视觉分组，
 * 勾选联动 R1-R10 与共享 selectedResultIds 不变。
 */
import { useState } from 'react'

/** 用例层组织维度（分组视图 / 标签视图） */
export type PickOrgDimension = 'group' | 'tag'

/** 子视图（平铺 / 交叉：分组视图内按标签、标签视图内按用例分组） */
export type PickSubView = 'flat' | 'byTag' | 'byGroup'

export interface PickOrgState {
  org: PickOrgDimension
  subView: PickSubView
  setOrg: (org: PickOrgDimension) => void
  setSubView: (subView: PickSubView) => void
}

/**
 * 阶段 2 三视图共享组织状态（会话态，不进 URL；切换视图保持组织偏好）。
 * 由 pick-step 实例化一次，下发用例视图与设备/结果类型视图的用例层组织。
 */
export function usePickOrg(
  initialOrg: PickOrgDimension = 'group',
  initialSubView: PickSubView = 'flat'
): PickOrgState {
  const [org, setOrg] = useState<PickOrgDimension>(initialOrg)
  const [subView, setSubView] = useState<PickSubView>(initialSubView)
  return { org, subView, setOrg, setSubView }
}
