/**
 * 「按当前筛选导出」范围圈定（features/testcases/lib，INT-1642 导出接线）。
 *
 * 取数口径按筛选态分流（不写兼容层，各走各的契约）：
 * - 收藏态：POST /testcases/ids 不认 favorite（后端族 fetch_case_ids 会**静默返回全库**，代码审计 P2），
 *   改走列表端点 GET /testcases?favorite=true 逐页翻完（收藏集本身很小，服务端已收窄，实测 0.2s）；
 * - 未分组虚拟组：group_id 无哨兵，列表端点不带 group_id 拉全量后按 groupId=null 前端过滤，同样逐页翻完；
 * - 其余（搜索 / 分组 / 标签 / 维度 / 算法 / 回收站）：仍走 POST /testcases/ids（轻量 id 查询，
 *   实测 0.0s，列表整页扫描 7s，不必退化）。
 * 全量圈定与 id 查询实现由页面注入，纯逻辑在此单测。
 */
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import type { TestCaseListQuery } from '@/infrastructure/api/testcases-api'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import { UNGROUPED_GROUP_ID } from '@/features/testcases/constants'

/** 页面注入的取数依赖（infrastructure 实现；失败向上抛，弹窗 toast 透出） */
export interface ExportScopeDeps {
  /** 列表端点逐页翻完全量 id（fetchAllTestCaseIdsByFilter） */
  fetchAllIds: (query: TestCaseListQuery) => Promise<string[]>
  /** POST /testcases/ids 全量 id 圈定（fetchCaseIdsByFilter） */
  fetchIdsByFilter: (query: TestCaseListQuery) => Promise<string[]>
  /** 分组列表（把 groupId 换成 /ids 契约认的分组名） */
  groups: TestCaseGroup[]
  /** 当前已加载用例行（分组表未就绪时的兜底） */
  loadedItems: TestCaseListItem[]
}

/** 筛选态 → 列表端点查询（trim 搜索词；空串不传，避免后端把空串当条件） */
export function buildExportListQuery(
  filters: TestCaseListFilters
): TestCaseListQuery {
  return {
    search: filters.search?.trim() || undefined,
    groupId: filters.groupId ?? undefined,
    tag: filters.tag ?? undefined,
    dimensionId: filters.dimensionId ?? undefined,
    algorithmType: filters.algorithmType,
    favorite: filters.favorite,
    trash: filters.trash,
  }
}

/** 解析「当前筛选」全量 id（导出范围=按当前筛选条件） */
export async function resolveExportIds(
  filters: TestCaseListFilters,
  deps: ExportScopeDeps
): Promise<string[]> {
  // 收藏态：/ids 不认 favorite → 列表端点逐页翻（导出的就是界面上看到的收藏集）
  if (filters.favorite && !filters.trash) {
    return deps.fetchAllIds(buildExportListQuery(filters))
  }
  // 未分组虚拟组：同样以列表口径前端按 groupId=null 过滤后逐页翻完（不再只拿已加载行）
  if (filters.groupId === UNGROUPED_GROUP_ID) {
    return deps.fetchAllIds(buildExportListQuery(filters))
  }
  const groupName = deps.groups.find((g) => g.id === filters.groupId)?.name
  // 分组列表未就绪时不要退化成「全库」：以当前已加载的该分组行兜底
  if (filters.groupId && !groupName) {
    return deps.loadedItems
      .filter((c) => c.groupId === filters.groupId)
      .map((c) => c.id)
  }
  return deps.fetchIdsByFilter({
    search: filters.search?.trim() || undefined,
    group: groupName,
    tag: filters.tag,
    dimensionId: filters.dimensionId,
    algorithmType: filters.algorithmType,
    trash: filters.trash,
  })
}
