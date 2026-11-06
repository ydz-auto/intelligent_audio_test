/**
 * 会话级 per-card 状态 hook（application 层，11_用例域.md §3.5/§3.6/§9）。
 * groupSubView：分组卡内「平铺|按标签」子视图（key=分组 id）；
 * tagSubView：标签卡内「平铺|按用例分组」子视图（key=标签名）。
 * 「本会话内存、不进 URL」口径（与展开态同机制；刷新回默认「平铺」）。
 */
import { create } from 'zustand'

export type GroupSubView = 'flat' | 'byTag'
export type TagSubView = 'flat' | 'byGroup'

type SessionMapState = {
  /** 分组卡子视图（Record<groupId, 'flat'|'byTag'>；缺省=flat） */
  groupSubView: Record<string, GroupSubView>
  /** 标签卡子视图（Record<tagName, 'flat'|'byGroup'>；缺省=flat） */
  tagSubView: Record<string, TagSubView>
  setGroupSubView: (key: string, value: GroupSubView) => void
  setTagSubView: (key: string, value: TagSubView) => void
}

export const useSessionMap = create<SessionMapState>((set) => ({
  groupSubView: {},
  tagSubView: {},

  setGroupSubView: (key, value) =>
    set((s) => ({ groupSubView: { ...s.groupSubView, [key]: value } })),

  setTagSubView: (key, value) =>
    set((s) => ({ tagSubView: { ...s.tagSubView, [key]: value } })),
}))
